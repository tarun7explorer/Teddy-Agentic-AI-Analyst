"""Conservative verification: source provenance plus deterministic numeric checks."""

import re

from pydantic import ValidationError

from backend.agents.state import ClaimVerification, SafeErrorCode, VerificationResults
from backend.services.schemas import SupportedFinding
from backend.tools.calculate_statistics import NumericCalculation
from backend.tools.registry import ToolNotAllowed, ToolRegistry, ToolExecutionError
from backend.tools.validate_citations import (
    CitationEvidence,
    ClaimForCitationCheck,
    ValidateCitationsOutput,
)


_DATE_TEXT = re.compile(
    r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\w])(?P<unit>[$\u20ac\u00a3])?\s*(?P<number>[+-]?\d[\d,]*(?:\.\d+)?)(?P<percent>\s*%)?")
_STOP_LABEL_WORDS = {"the", "and", "for", "was", "were", "with", "from", "that", "this", "total", "mean", "sum", "average"}


def _numbers_in_claim(text: str) -> list[tuple[float, str | None]]:
    without_dates = _DATE_TEXT.sub(" ", text)
    numbers: list[tuple[float, str | None]] = []
    for match in _NUMBER.finditer(without_dates):
        try:
            value = float(match.group("number").replace(",", ""))
        except (TypeError, ValueError, OverflowError):
            continue
        if not value.is_integer() or not 1800 <= value <= 2199:
            unit = match.group("unit") or ("%" if match.group("percent") else None)
            numbers.append((value, unit))
    return numbers


def _claim_label_tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[\w]+", text)
        if len(token) > 2 and token.casefold() not in _STOP_LABEL_WORDS
    }


def _relevant_calculations(
    claim: str,
    calculations: list[NumericCalculation],
) -> list[NumericCalculation]:
    tokens = _claim_label_tokens(claim)
    if not tokens:
        return []
    matches = []
    for item in calculations:
        label_tokens = _claim_label_tokens(item.label)
        if tokens & label_tokens:
            matches.append(item)
    return matches


def _numeric_result(
    claim: str,
    calculations: list[NumericCalculation],
) -> tuple[str | None, str | None]:
    mentions = _numbers_in_claim(claim)
    if not mentions:
        return None, None
    relevant = _relevant_calculations(claim, calculations)
    if not relevant:
        return "unverified", "numeric_result_not_available_for_claim_label"
    for value, unit in mentions:
        equal_value = [
            item for item in relevant
            if abs(float(item.value) - value) <= max(1e-8, abs(value) * 1e-8)
        ]
        if not equal_value:
            return "contradicted", "numeric_value_conflicts_with_deterministic_calculation"
        if unit is None:
            if any(item.unit is not None for item in equal_value):
                return "unverified", "claim_omits_calculation_unit"
        elif not any(item.unit == unit for item in equal_value):
            return "unverified", "claim_unit_does_not_match_calculation_unit"
    return "partially_verified", "numeric_values_match_calculations_but_claim_logic_is_not_proven"


class VerificationAgent:
    async def verify_findings(
        self,
        *,
        document_id: str,
        findings: list[SupportedFinding],
        calculations: list[NumericCalculation],
        registry: ToolRegistry,
    ) -> VerificationResults:
        if not findings:
            return VerificationResults(status="not_run")
        bounded_findings = findings[:500]
        claims = [
            ClaimForCitationCheck(
                claim_id=f"claim-{index}",
                evidence=[
                    CitationEvidence(
                        document_id=document_id,
                        source_id=citation.source_id,
                        reference=citation.reference,
                        quote=citation.quote,
                    )
                    for citation in finding.citations[:8]
                ],
            )
            for index, finding in enumerate(bounded_findings)
        ]
        try:
            raw = await registry.execute("validate_citations", {
                "document_id": document_id,
                "claims": claims,
            })
            citation_results = ValidateCitationsOutput.model_validate(raw)
        except (ToolNotAllowed, ToolExecutionError, ValidationError, ValueError):
            return VerificationResults(
                status="partial",
                claims_checked=len(bounded_findings),
                rejected_claim_count=len(bounded_findings),
                unresolved_warnings=["Citation provenance verification could not complete."],
            )

        by_id = {item.claim_id: item for item in citation_results.claims}
        verified_claims: list[ClaimVerification] = []
        accepted_count = 0
        rejected_count = 0
        for index, finding in enumerate(bounded_findings):
            claim_id = f"claim-{index}"
            citation_check = by_id.get(claim_id)
            citations = citation_check.verified_citations if citation_check else []
            source_ids = list(dict.fromkeys(item.source_id for item in citations))[:8]
            reasons: list[str] = []
            if not citations:
                status = "unverified"
                reasons.extend(citation_check.reasons if citation_check else ["citation_check_missing"])
                reasons.append("no_valid_source_quote")
            else:
                numeric_status, numeric_reason = _numeric_result(finding.text, calculations)
                if numeric_status == "contradicted":
                    status = "contradicted"
                    reasons.append(numeric_reason or "numeric_inconsistency")
                elif numeric_status == "unverified":
                    status = "unverified"
                    reasons.append(numeric_reason or "numeric_result_not_available")
                else:
                    # Exact quote provenance is necessary, but does not establish
                    # that a natural-language claim logically follows from the quote.
                    status = "partially_verified"
                    reasons.append("source_quote_matches; entailment_not_proven")
                    if numeric_reason:
                        reasons.append(numeric_reason)

            if status == "partially_verified":
                accepted_count += 1
            else:
                rejected_count += 1
            verified_claims.append(ClaimVerification(
                claim=finding.text,
                status=status,
                source_ids=source_ids,
                reasons=list(dict.fromkeys(reasons))[:8],
            ))

        if rejected_count == 0:
            overall = "partial"  # Quote presence is not a full entailment check.
            warnings = ["Citations and available numeric results were checked; semantic entailment remains unproven."]
        elif accepted_count == 0:
            overall = "failed"
            warnings = ["No claims passed the available source and numeric checks."]
        else:
            overall = "partial"
            warnings = ["Some claims were unsupported or numerically inconsistent."]
        return VerificationResults(
            status=overall,
            claims_checked=len(bounded_findings),
            claims_with_valid_sources=accepted_count,
            rejected_claim_count=rejected_count,
            claim_results=verified_claims,
            unresolved_warnings=warnings,
        )
