"""Create safe, document-scoped Markdown, CSV, and PDF exports."""

import csv
import io
import re
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _reference(reference: dict[str, Any] | None) -> str:
    if not reference:
        return "Source reference unavailable"
    return ", ".join(f"{key}: {value}" for key, value in reference.items() if value is not None)


def _citations(items: list[dict[str, Any]] | None) -> str:
    return " ".join(
        f"Source ({_reference(item.get('reference'))}): “{_text(item.get('quote'))}”"
        for item in (items or [])
    )


def summary_markdown(document: Any) -> str:
    analysis = document.analysis
    if analysis is None:
        raise ValueError("A generated summary is not available for this document yet.")
    lines = [f"# Summary: {document.original_filename}", "", "## Executive summary"]
    summary = analysis.get("five_line_summary") or []
    if summary:
        for item in summary:
            lines.append(f"- {_text(item.get('text'))}")
            citation = _citations(item.get("citations"))
            if citation:
                lines.append(f"  \n  {citation}")
    else:
        lines.append("Summary unavailable: no executive summary was generated.")

    detailed = analysis.get("detailed_summary") or {}
    lines.extend(["", "## Detailed summary", _text(detailed.get("text")) or "Detailed summary unavailable."])
    citation = _citations(detailed.get("citations"))
    if citation:
        lines.extend(["", citation])

    sections = [
        ("Key findings", "key_takeaways"),
        ("Important names, dates, and figures", "important_entities"),
        ("Risks", "risks"),
        ("Decisions", "decisions"),
        ("Action items", "action_items"),
    ]
    for heading, key in sections:
        findings = analysis.get(key) or []
        lines.extend(["", f"## {heading}"])
        if not findings:
            lines.append("No supported findings available.")
        for finding in findings:
            category = finding.get("category")
            label = f"**{_text(category)}:** " if category else ""
            lines.append(f"- {label}{_text(finding.get('text'))}")
            citation = _citations(finding.get("citations"))
            if citation:
                lines.append(f"  \n  {citation}")
    return "\n".join(lines).rstrip() + "\n"


def table_csv(table: dict[str, Any]) -> str:
    rows = table.get("rows") or []
    columns = list(table.get("columns") or [])
    if not columns and rows:
        if isinstance(rows[0], dict):
            columns = list(rows[0])
        elif isinstance(rows[0], (list, tuple)):
            columns = [f"Column {index + 1}" for index in range(max(map(len, rows)))]
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow([_safe_csv_cell(column) for column in columns])
    for row in rows:
        values = [row.get(column, "") for column in columns] if isinstance(row, dict) else list(row)
        safe = [_safe_csv_cell(value) for value in values[:len(columns)]]
        safe.extend([""] * (len(columns) - len(safe)))
        writer.writerow(safe)
    return output.getvalue()


def _safe_csv_cell(value: Any) -> str:
    value_text = _text(value)
    formula_like = value_text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
    negative_number = re.fullmatch(r"\s*-\d+(?:\.\d+)?\s*", value_text) is not None
    return "'" + value_text if formula_like and not negative_number else value_text


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    # Paragraph supports markup; escape every filename, source quote, and model string.
    safe = escape(_text(value)).replace("\n", "<br/>")
    return Paragraph(safe or " ", style)


def report_pdf(document: Any) -> bytes:
    buffer = io.BytesIO()
    output = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.65 * inch,
        rightMargin=.65 * inch,
        topMargin=.6 * inch,
        bottomMargin=.6 * inch,
        title=f"Teddy report - {document.original_filename}",
        author="Teddy – Smart AI Analyst",
    )
    defaults = getSampleStyleSheet()
    title = ParagraphStyle("TeddyTitle", parent=defaults["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#252b47"))
    heading = ParagraphStyle("TeddyHeading", parent=defaults["Heading2"], textColor=colors.HexColor("#514b9a"), spaceBefore=11, spaceAfter=5)
    body = ParagraphStyle("TeddyBody", parent=defaults["BodyText"], leading=14, spaceAfter=5, wordWrap="CJK")
    small = ParagraphStyle("TeddySmall", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#656a7a"))
    story: list[Any] = [
        _paragraph("Teddy · Document analysis report", title),
        _paragraph(f"Document: {document.original_filename}", body),
        Spacer(1, 8),
    ]
    analysis = document.analysis or {}
    story.append(_paragraph("Executive summary", heading))
    summary = analysis.get("five_line_summary") or []
    if summary:
        for number, item in enumerate(summary, 1):
            story.append(_paragraph(f"{number}. {_text(item.get('text'))}", body))
            citation = _citations(item.get("citations"))
            if citation:
                story.append(_paragraph(citation, small))
    else:
        story.append(_paragraph("Summary unavailable: analysis has not been generated for this document.", body))
    detailed = analysis.get("detailed_summary") or {}
    if detailed.get("text"):
        story.extend([_paragraph("Detailed summary", heading), _paragraph(detailed["text"], body)])
        citation = _citations(detailed.get("citations"))
        if citation:
            story.append(_paragraph(citation, small))

    for heading_text, key in [
        ("Key findings", "key_takeaways"),
        ("Important names, dates, and figures", "important_entities"),
        ("Risks", "risks"), ("Decisions", "decisions"), ("Action items", "action_items"),
    ]:
        findings = analysis.get(key) or []
        story.append(_paragraph(heading_text, heading))
        if not findings:
            story.append(_paragraph("No supported findings available.", body))
        for finding in findings:
            category = finding.get("category")
            statement = f"{category}: {finding.get('text')}" if category else finding.get("text")
            story.append(_paragraph(f"• {_text(statement)}", body))
            citation = _citations(finding.get("citations"))
            if citation:
                story.append(_paragraph(citation, small))

    analytics = document.analytics or {}
    story.append(_paragraph("Calculated statistics", heading))
    metrics = analytics.get("metrics") or []
    if metrics:
        rows = [["Metric", "Statistic", "Value", "Unit", "Source"]]
        rows.extend([
            [_text(item.get("label")), _text(item.get("statistic")), _text(item.get("value")),
             _text(item.get("unit")), _reference(item.get("source_reference"))]
            for item in metrics
        ])
        table = Table([[_paragraph(cell, small) for cell in row] for row in rows], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeecfa")),
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#dfdeea")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(table)
    else:
        story.append(_paragraph("No calculated statistics are available for this document.", body))

    story.append(_paragraph("Charts and chart data", heading))
    charts = analytics.get("charts") or []
    if not charts:
        story.append(_paragraph("No supported charts or chart data are available.", body))
    for chart in charts:
        story.append(_paragraph(f"{_text(chart.get('title'))} ({_text(chart.get('chart_type'))})", body))
        story.append(_paragraph(
            f"Source: {_reference(chart.get('source_reference'))}. Aggregation: "
            f"{_text(chart.get('aggregation'))}. Unit: {_text(chart.get('unit')) or 'not specified'}.", small,
        ))
        series = chart.get("series") or []
        rows = [["Label"] + [_text(item.get("name")) for item in series]]
        for index, label in enumerate(chart.get("labels") or []):
            rows.append([_text(label)] + [
                _text(item.get("data", [])[index]) if index < len(item.get("data", [])) else ""
                for item in series
            ])
        table = Table([[_paragraph(cell, small) for cell in row] for row in rows], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f0f8")),
            ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#e1e0e9")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.extend([table, Spacer(1, 6)])

    story.append(_paragraph("Source references", heading))
    if document.source_references:
        story.extend(_paragraph(f"• {_reference(reference)}", small) for reference in document.source_references)
    else:
        story.append(_paragraph("No source references were extracted.", body))
    output.build(story)
    return buffer.getvalue()


def safe_export_stem(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")[:80]
    return stem or "teddy-document"
