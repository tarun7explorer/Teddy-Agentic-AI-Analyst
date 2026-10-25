"use strict";

const fileInput = document.querySelector("#file-input");
const dropzone = document.querySelector("#dropzone");
const browseButton = document.querySelector("#browse-button");
const dropTitle = document.querySelector("#drop-title");
const dropSubtitle = document.querySelector("#drop-subtitle");
const selectionStatus = document.querySelector("#selection-status");
const uploadActions = document.querySelector("#upload-actions");
const submitUpload = document.querySelector("#submit-upload");
const removeSelection = document.querySelector("#remove-selection");
const uploadProgress = document.querySelector("#upload-progress");
const uploadStage = document.querySelector("#upload-stage");
const uploadPercent = document.querySelector("#upload-percent");
const progressFill = document.querySelector("#upload-progress-fill");
const uploadError = document.querySelector("#upload-error");
const analyzeButton = document.querySelector("#analyze-document");
const downloadSummaryButton = document.querySelector("#download-summary");
const downloadReportButton = document.querySelector("#download-report");
const newAnalysisButton = document.querySelector("#new-analysis");
const deleteDocumentButton = document.querySelector("#delete-document");
const downloadStatus = document.querySelector("#download-status");
const downloadError = document.querySelector("#download-error");
const analysisState = document.querySelector("#analysis-state");
const analysisStateText = document.querySelector("#analysis-state-text");
const analysisError = document.querySelector("#analysis-error");
const analysisOutput = document.querySelector("#analysis-output");
const analysisModel = document.querySelector("#analysis-model");
const summaryList = document.querySelector("#summary-list");
const detailedSummary = document.querySelector("#detailed-summary");
const findingsList = document.querySelector("#findings-list");
const analysisWarnings = document.querySelector("#analysis-warnings");
const workflowOverview = document.querySelector("#workflow-overview");
const workflowStatus = document.querySelector("#workflow-status");
const workflowQuality = document.querySelector("#workflow-quality");
const workflowProvider = document.querySelector("#workflow-provider");
const workflowVerification = document.querySelector("#workflow-verification");
const workflowWarnings = document.querySelector("#workflow-warnings");
const documentHighlights = document.querySelector("#document-highlights");
const highlightsEmpty = document.querySelector("#highlights-empty");
const highlightsEmptyCaption = document.querySelector("#highlights-empty-caption");
const dashboardSummaryEmpty = document.querySelector("#summary-empty");
const dashboardSummaryContent = document.querySelector("#summary-content");
const dashboardSummaryList = document.querySelector("#dashboard-summary-list");
const dashboardDetailedSummary = document.querySelector("#dashboard-detailed-summary");
const insightPlaceholders = document.querySelector("#insight-placeholders");
const dashboardInsights = document.querySelector("#dashboard-insights");
const insightsEmptyCaption = document.querySelector("#insights-empty-caption");
const chatEmpty = document.querySelector("#chat-empty");
const chatEmptyTitle = document.querySelector("#chat-empty-title");
const chatEmptyMessage = document.querySelector("#chat-empty-message");
const chatSuggestions = document.querySelector("#chat-suggestions");
const chatMessages = document.querySelector("#chat-messages");
const chatForm = document.querySelector("#chat-form");
const chatQuestion = document.querySelector("#chat-question");
const chatSend = document.querySelector("#chat-send");
const chatStatus = document.querySelector("#chat-status");
const chatError = document.querySelector("#chat-error");
const chatLimitNote = document.querySelector("#chat-limit-note");

const resultPanel = document.querySelector("#document-results");
const resultMeta = document.querySelector("#result-meta");
const resultWarnings = document.querySelector("#result-warnings");
const extractionEmpty = document.querySelector("#extraction-empty");
const extractionEmptyMessage = document.querySelector("#extraction-empty-message");
const textBlock = document.querySelector("#extracted-text-block");
const extractedText = document.querySelector("#extracted-text");
const textCharacterCount = document.querySelector("#text-character-count");
const sourceBlock = document.querySelector("#source-list-block");
const sourceChips = document.querySelector("#source-chips");
const tablesBlock = document.querySelector("#tables-block");
const tableCount = document.querySelector("#table-count");
const tablePreviews = document.querySelector("#table-previews");

const defaultLimits = {
  max_upload_size_bytes: 10 * 1024 * 1024,
  max_upload_size_mb: 10,
  max_chat_question_chars: 1000,
  supported_extensions: [".pdf", ".docx", ".xlsx", ".csv", ".txt"],
};
const state = { file: null, documentId: null, busy: false, analyzing: false, chatBusy: false, downloading: false, deleting: false, limits: defaultLimits };

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileExtension(file) {
  return `.${file.name.split(".").pop().toLowerCase()}`;
}

function setBusy(busy) {
  state.busy = busy;
  submitUpload.disabled = busy;
  removeSelection.disabled = busy;
  browseButton.disabled = busy;
  browseButton.textContent = busy ? "Uploading…" : "Browse files ↗";
}

function clearUploadError() {
  uploadError.hidden = true;
  uploadError.textContent = "";
}

function showUploadError(message) {
  uploadError.textContent = message;
  uploadError.hidden = false;
}

function clearResults() {
  window.TeddyCharts?.clear();
  resultPanel.hidden = true;
  resultMeta.textContent = "";
  resultWarnings.replaceChildren();
  resultWarnings.hidden = true;
  extractedText.textContent = "";
  sourceChips.replaceChildren();
  tablePreviews.replaceChildren();
  analysisState.hidden = true;
  analysisError.hidden = true;
  analysisError.textContent = "";
  analysisOutput.hidden = true;
  analysisOutput.dataset.ready = "false";
  analyzeButton.disabled = false;
  analyzeButton.textContent = "Analyze with Teddy";
  downloadSummaryButton.disabled = true;
  downloadStatus.hidden = true;
  downloadStatus.textContent = "";
  downloadError.hidden = true;
  downloadError.textContent = "";
  summaryList.replaceChildren();
  detailedSummary.replaceChildren();
  findingsList.replaceChildren();
  dashboardSummaryList.replaceChildren();
  dashboardDetailedSummary.textContent = "";
  dashboardSummaryContent.hidden = true;
  dashboardSummaryEmpty.hidden = false;
  dashboardInsights.replaceChildren();
  dashboardInsights.hidden = true;
  insightPlaceholders.hidden = false;
  insightsEmptyCaption.hidden = false;
  analysisWarnings.replaceChildren();
  analysisWarnings.hidden = true;
  workflowOverview.hidden = true;
  workflowWarnings.replaceChildren();
  workflowWarnings.hidden = true;
  documentHighlights.replaceChildren();
  documentHighlights.hidden = true;
  highlightsEmpty.hidden = false;
  highlightsEmptyCaption.hidden = false;
  resetChat();
}

function resetChat() {
  state.chatBusy = false;
  chatQuestion.value = "";
  chatQuestion.disabled = true;
  chatSend.disabled = true;
  chatEmpty.hidden = false;
  chatEmptyTitle.textContent = "Good questions start with context.";
  chatEmptyMessage.textContent = "Upload a document to start a grounded conversation. Teddy will answer from extracted passages and show the sources it used.";
  chatSuggestions.replaceChildren();
  chatMessages.replaceChildren();
  chatStatus.hidden = true;
  chatError.hidden = true;
  chatError.textContent = "";
}

async function deleteDocument(documentId) {
  if (!documentId) return true;
  try {
    const response = await fetch(`/api/v1/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" });
    return response.ok || response.status === 404;
  } catch {
    return false;
  }
}

function resetSelection({ deleteStored = true } = {}) {
  const oldDocumentId = state.documentId;
  state.file = null;
  state.documentId = null;
  fileInput.value = "";
  dropTitle.textContent = "Drag your file here";
  dropSubtitle.textContent = "or choose one from your device";
  selectionStatus.textContent = "Files are extracted by Teddy’s backend. Review the local analytics, ask document-scoped questions, and request an AI summary when an approved provider is available.";
  uploadActions.hidden = true;
  uploadProgress.hidden = true;
  progressFill.style.width = "0%";
  clearUploadError();
  clearResults();
  if (deleteStored && oldDocumentId) {
    deleteDocument(oldDocumentId).then((deleted) => {
      if (!deleted) selectionStatus.textContent = "The document could not be deleted now and will expire automatically.";
    });
  }
}

function selectFile(file) {
  if (!file || state.busy || state.analyzing || state.chatBusy || state.downloading || state.deleting) return;
  clearUploadError();
  if (state.documentId) deleteDocument(state.documentId);
  state.documentId = null;
  clearResults();

  const extension = fileExtension(file);
  if (!state.limits.supported_extensions.includes(extension)) {
    state.file = null;
    uploadActions.hidden = true;
    showUploadError("This file type is not supported yet. Choose a PDF, DOCX, XLSX, CSV, or TXT file.");
    return;
  }
  if (file.size === 0) {
    state.file = null;
    uploadActions.hidden = true;
    showUploadError("This file is empty. Choose a document that contains content.");
    return;
  }
  if (file.size > state.limits.max_upload_size_bytes) {
    state.file = null;
    uploadActions.hidden = true;
    showUploadError(`This file exceeds Teddy’s ${state.limits.max_upload_size_mb} MB upload limit.`);
    return;
  }

  state.file = file;
  dropTitle.textContent = file.name;
  dropSubtitle.textContent = `${formatBytes(file.size)} · ${extension.slice(1).toUpperCase()} file`;
  selectionStatus.textContent = "Ready to upload. Teddy will extract the document’s text and available tables; no AI analysis is performed yet.";
  uploadActions.hidden = false;
}

function appendTextElement(parent, tag, text, className) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = text;
  parent.append(element);
  return element;
}

function renderWorkflow(workflow, analysis = null) {
  if (!workflow) return;
  workflowOverview.hidden = false;
  const statusLabel = {
    not_started: "Extraction complete · analysis not started",
    created: "Workflow created",
    running: "Workflow running",
    completed: "Workflow completed",
    partial: "Partial result · some checks or steps are incomplete",
    failed: "Workflow failed",
  }[workflow.status] || "Workflow status unavailable";
  workflowStatus.textContent = `${statusLabel}. ${workflow.document_assessment?.passage_count || 0} passages, ${workflow.document_assessment?.table_count || 0} tables, ${workflow.document_assessment?.source_reference_count || 0} source references.`;

  const assessment = workflow.document_assessment || {};
  workflowQuality.textContent = `Extraction quality: ${assessment.extraction_quality || "unknown"}`;
  workflowQuality.dataset.quality = assessment.extraction_quality || "unknown";
  const providerStatus = workflow.provider_status || {};
  workflowProvider.textContent = providerStatus.available
    ? `AI provider available: ${providerStatus.provider}. ${providerStatus.message || ""}`
    : `AI unavailable: ${providerStatus.message || "AI analysis is disabled. Local extraction, analytics, and exports remain available."}`;

  const verification = workflow.verification || {};
  if (verification.claims_checked) {
    workflowVerification.textContent = `Verification: ${verification.status}. ${verification.claims_with_valid_sources || 0} claims have source matches; quote matching does not prove logical entailment.`;
  } else if (workflow.status === "not_started") {
    workflowVerification.textContent = "Verification has not run yet.";
  } else {
    workflowVerification.textContent = "No claims were available to verify.";
  }

  workflowWarnings.replaceChildren();
  const messages = [
    ...(workflow.warnings || []).map((item) => item.message),
    ...(assessment.unsupported_content || []).map((item) => `Coverage limitation: ${item.replaceAll("_", " ")}.`),
    ...(verification.unresolved_warnings || []),
  ].filter(Boolean);
  workflowWarnings.hidden = messages.length === 0;
  for (const warning of messages.slice(0, 40)) appendTextElement(workflowWarnings, "li", warning);

  const evidence = [...(workflow.evidence || [])];
  if (!evidence.length && analysis) {
    const findings = [
      ...(analysis.five_line_summary || []), analysis.detailed_summary,
      ...(analysis.key_takeaways || []), ...(analysis.risks || []),
    ].filter(Boolean);
    const seen = new Set();
    for (const finding of findings) for (const citation of finding.citations || []) {
      const key = `${citation.source_id}|${citation.quote}`;
      if (citation.quote && !seen.has(key)) {
        seen.add(key);
        evidence.push(citation);
      }
    }
  }
  documentHighlights.replaceChildren();
  for (const item of evidence.slice(0, 8)) {
    const entry = document.createElement("article");
    entry.className = "document-highlight";
    appendTextElement(entry, "span", formatReference(item.reference), "highlight-reference");
    appendTextElement(entry, "blockquote", item.quote, "highlight-quote");
    documentHighlights.append(entry);
  }
  const hasEvidence = documentHighlights.childElementCount > 0;
  documentHighlights.hidden = !hasEvidence;
  highlightsEmpty.hidden = hasEvidence;
  highlightsEmptyCaption.hidden = hasEvidence;
  if (!hasEvidence && workflow.status !== "not_started") {
    highlightsEmptyCaption.textContent = "No source excerpts were returned for this workflow.";
  }
}

function renderWarnings(warnings) {
  resultWarnings.replaceChildren();
  if (!warnings?.length) {
    resultWarnings.hidden = true;
    return;
  }
  resultWarnings.hidden = false;
  for (const warning of warnings) appendTextElement(resultWarnings, "p", warning, "warning-item");
}

function renderSources(references) {
  sourceChips.replaceChildren();
  if (!references?.length) {
    sourceBlock.hidden = true;
    return;
  }
  sourceBlock.hidden = false;
  const labels = references.slice(0, 24).map((source) => {
    if (source.type === "page") return `Page ${source.page}`;
    if (source.type === "sheet") return `Sheet: ${source.sheet}`;
    if (source.type === "table") return `Table ${source.table}`;
    if (source.type === "paragraph") return `Paragraph ${source.paragraph}`;
    if (source.type === "csv") return `Rows ${source.row_start}–${source.row_end}`;
    return source.type || "Source";
  });
  for (const label of labels) appendTextElement(sourceChips, "span", label, "source-chip");
  if (references.length > labels.length) {
    appendTextElement(sourceChips, "span", `+${references.length - labels.length} more`, "source-chip muted-chip");
  }
}

function renderTable(table, tableIndex) {
  const details = document.createElement("details");
  details.className = "table-preview";
  const summary = document.createElement("summary");
  const source = table.source_reference?.sheet ? ` · Sheet: ${table.source_reference.sheet}` : "";
  summary.textContent = `${table.name || "Extracted table"}${source} · ${table.row_count ?? table.rows?.length ?? 0} rows`;
  details.append(summary);

  const rows = Array.isArray(table.rows) ? table.rows : [];
  const columns = Array.isArray(table.columns) && table.columns.length
    ? table.columns
    : [...new Set(rows.flatMap((row) => Array.isArray(row) ? row.map((_, index) => `Column ${index + 1}`) : Object.keys(row || {})))];
  const tableElement = document.createElement("table");
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (const column of columns) appendTextElement(headerRow, "th", String(column));
  thead.append(headerRow);
  tableElement.append(thead);

  const tbody = document.createElement("tbody");
  for (const row of rows.slice(0, 12)) {
    const tr = document.createElement("tr");
    for (let index = 0; index < columns.length; index += 1) {
      const value = Array.isArray(row) ? row[index] : row?.[columns[index]];
      appendTextElement(tr, "td", value == null ? "" : String(value));
    }
    tbody.append(tr);
  }
  tableElement.append(tbody);
  const scroll = document.createElement("div");
  scroll.className = "table-scroll";
  scroll.append(tableElement);
  details.append(scroll);
  const csvButton = document.createElement("button");
  csvButton.type = "button";
  csvButton.className = "export-action table-export-button";
  csvButton.textContent = "Download this table as CSV";
  csvButton.setAttribute("aria-label", `Download ${table.name || `table ${tableIndex + 1}`} as CSV`);
  csvButton.addEventListener("click", () => downloadExport("csv", tableIndex));
  details.append(csvButton);
  if (rows.length > 12) appendTextElement(details, "p", `Showing 12 of ${rows.length} extracted rows in this preview.`, "table-caption");
  if (table.truncated) appendTextElement(details, "p", "The source data was limited by the configured processing limit.", "table-caption");
  return details;
}

function renderResults(result) {
  state.documentId = result.document_id;
  resultPanel.hidden = false;
  const fileSize = formatBytes(result.file_size || 0);
  resultMeta.textContent = `${result.original_filename} · ${String(result.detected_file_type).toUpperCase()} · ${fileSize} · ${result.status}`;
  renderWarnings(result.warnings);
  renderWorkflow(result.workflow, result.analysis || null);

  const text = result.extracted_text || "";
  const hasTables = Array.isArray(result.tables) && result.tables.length > 0;
  const hasText = text.trim().length > 0;
  extractionEmpty.hidden = hasText || hasTables;
  extractionEmptyMessage.textContent = result.warnings?.[0] || "The file was accepted, but it did not contain extractable text or table data.";
  textBlock.hidden = !hasText;
  extractedText.textContent = text.slice(0, 30_000);
  if (text.length > 30_000) extractedText.textContent += "\n\n[Preview shortened. The complete extracted text remains available through the results API.]";
  textCharacterCount.textContent = `${text.length.toLocaleString()} characters`;
  renderSources(result.source_references);

  tablePreviews.replaceChildren();
  tablesBlock.hidden = !hasTables;
  if (hasTables) {
    tableCount.textContent = `${result.tables.length} ${result.tables.length === 1 ? "table" : "tables"}`;
    for (const [index, table] of result.tables.entries()) tablePreviews.append(renderTable(table, index));
  }
  if (result.analytics) window.TeddyCharts?.render(result.analytics);
  if (result.analysis) renderAnalysis(result.analysis);
  activateChat(result);
  document.querySelector("#workspace-heading").scrollIntoView({ behavior: "smooth", block: "start" });
}

function activateChat(result) {
  const hasContent = Boolean((result.extracted_text || "").trim() || result.tables?.length);
  chatQuestion.disabled = !hasContent;
  chatSend.disabled = !hasContent;
  chatEmptyTitle.textContent = hasContent ? "Ask about this document." : "No extractable content to discuss yet.";
  chatEmptyMessage.textContent = hasContent
    ? "Teddy searches the extracted passages for each question and shows the source quotes used."
    : "This document did not contain extracted text or tables, so chat is unavailable.";
  chatSuggestions.replaceChildren();
  if (!hasContent) return;

  const suggestions = ["What are the main points in this document?"];
  const firstTable = result.tables?.[0];
  if (firstTable) {
    const name = firstTable.name || "the extracted table";
    suggestions.push(`What does ${name} show?`);
    const columns = firstTable.columns || [];
    if (columns.length > 1) suggestions.push(`Explain the ${columns.slice(0, 2).join(" and ")} fields.`);
  } else {
    const firstPage = result.source_references?.find((reference) => reference.type === "page");
    if (firstPage) suggestions.push(`What is discussed on page ${firstPage.page}?`);
    if (/\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[/. -]\d{1,2}[/. -]\d{2,4}\b/.test(result.extracted_text || "")) {
      suggestions.push("Which dates or deadlines are mentioned?");
    }
  }
  for (const question of suggestions.slice(0, 3)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chat-suggestion";
    button.textContent = question;
    button.addEventListener("click", () => sendChatQuestion(question));
    chatSuggestions.append(button);
  }
}

function addChatMessage(role, text, { notFound = false, sources = [], workflow = null } = {}) {
  const message = document.createElement("article");
  message.className = `chat-message ${role === "user" ? "user-message" : "assistant-message"}`;
  appendTextElement(message, "span", role === "user" ? "You" : "Teddy", "chat-message-label");
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.textContent = text;
  if (notFound && role !== "user") bubble.classList.add("not-found-bubble");
  message.append(bubble);

  const verification = workflow?.verification;
  if (role !== "user" && verification?.claims_checked) {
    const note = `Verification: ${verification.status}. Source matches are provenance checks; they do not prove entailment.`;
    appendTextElement(message, "p", note, "chat-verification-note");
  }

  if (role !== "user" && sources.length) {
    const sourceList = document.createElement("div");
    sourceList.className = "chat-sources";
    for (const source of sources) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chat-source-button";
      button.textContent = formatReference(source.reference);
      button.addEventListener("click", () => {
        const target = source.reference?.type === "sheet" || source.reference?.type === "table"
          ? document.querySelector("#tables-block")
          : document.querySelector("#extracted-text-block");
        (target && !target.hidden ? target : document.querySelector("#document-results"))
          .scrollIntoView({ behavior: "smooth", block: "start" });
      });
      sourceList.append(button);
      if (source.quote) appendTextElement(sourceList, "span", `“${source.quote}”`, "chat-source-quote");
    }
    message.append(sourceList);
  }
  chatMessages.append(message);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendChatQuestion(questionText = chatQuestion.value) {
  const question = questionText.trim();
  if (!question || !state.documentId || state.chatBusy) return;
  if (question.length > state.limits.max_chat_question_chars) {
    chatError.textContent = `Questions must be ${state.limits.max_chat_question_chars} characters or fewer.`;
    chatError.hidden = false;
    return;
  }
  state.chatBusy = true;
  chatQuestion.value = "";
  chatQuestion.disabled = true;
  chatSend.disabled = true;
  browseButton.disabled = true;
  document.querySelector("#delete-document").disabled = true;
  chatEmpty.hidden = true;
  chatError.hidden = true;
  chatStatus.textContent = "Searching extracted passages and checking source evidence…";
  chatStatus.hidden = false;
  addChatMessage("user", question);
  try {
    const response = await fetch(`/api/v1/documents/${encodeURIComponent(state.documentId)}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `Chat request failed (${response.status}).`);
    addChatMessage("assistant", payload.answer, {
      notFound: payload.status === "not_found",
      sources: payload.sources || [],
      workflow: payload.workflow,
    });
    renderWorkflow(payload.workflow);
  } catch (error) {
    chatError.textContent = error.message || "Teddy could not answer right now. Please try again.";
    chatError.hidden = false;
    if (!chatQuestion.value) chatQuestion.value = question;
    fetch(`/api/v1/documents/${encodeURIComponent(state.documentId)}/results`)
      .then((response) => response.ok ? response.json() : null)
      .then((result) => { if (result?.workflow) renderWorkflow(result.workflow); })
      .catch(() => {});
  } finally {
    chatStatus.hidden = true;
    state.chatBusy = false;
    chatQuestion.disabled = false;
    chatSend.disabled = !chatQuestion.value.trim();
    browseButton.disabled = false;
    document.querySelector("#delete-document").disabled = false;
    chatQuestion.focus();
  }
}

function formatReference(reference) {
  if (reference?.type === "page") return `Page ${reference.page}`;
  if (reference?.type === "sheet") return `Sheet ${reference.sheet}${reference.row_start ? ` · Row ${reference.row_start}` : ""}`;
  if (reference?.type === "csv") return `CSV row ${reference.row_start}`;
  if (reference?.type === "paragraph") return `Paragraph ${reference.paragraph}`;
  if (reference?.type === "table") return `Table ${reference.table}`;
  if (reference?.type === "text") {
    if (reference.line_start != null && reference.line_end != null) return `Lines ${reference.line_start}–${reference.line_end}`;
    return "Text source";
  }
  return "Document source";
}

function appendCitationList(parent, citations) {
  if (!citations?.length) return;
  const container = document.createElement("div");
  container.className = "citation-list";
  for (const citation of citations) {
    const details = document.createElement("details");
    details.className = "citation-detail";
    appendTextElement(details, "summary", formatReference(citation.reference));
    appendTextElement(details, "blockquote", `“${citation.quote}”`);
    container.append(details);
  }
  parent.append(container);
}

function renderSummaryLines(target, lines) {
  target.replaceChildren();
  for (const line of lines || []) {
    const item = document.createElement("li");
    appendTextElement(item, "p", line.text);
    appendCitationList(item, line.citations);
    target.append(item);
  }
}

function renderFindingGroup(parent, heading, items, categoryClass = "") {
  if (!items?.length) return;
  const group = document.createElement("section");
  group.className = `finding-group ${categoryClass}`.trim();
  appendTextElement(group, "h5", heading);
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "finding-item";
    if (item.category) appendTextElement(card, "span", item.category, "finding-category");
    appendTextElement(card, "p", item.text);
    appendCitationList(card, item.citations);
    group.append(card);
  }
  parent.append(group);
}

function renderAnalysis(analysis) {
  analysisOutput.hidden = false;
  analysisOutput.dataset.ready = "true";
  analysisState.hidden = true;
  analysisError.hidden = true;
  analyzeButton.disabled = true;
  analyzeButton.textContent = "Analysis complete";
  downloadSummaryButton.disabled = false;
  analysisModel.textContent = `AI-generated findings · ${analysis.model || "configured provider"}`;
  renderWorkflow(analysis.workflow, analysis);

  renderSummaryLines(summaryList, analysis.five_line_summary);
  renderSummaryLines(dashboardSummaryList, analysis.five_line_summary);
  detailedSummary.replaceChildren();
  appendTextElement(detailedSummary, "p", analysis.detailed_summary?.text || "No source-supported detailed summary was returned.");
  appendCitationList(detailedSummary, analysis.detailed_summary?.citations);
  dashboardDetailedSummary.textContent = analysis.detailed_summary?.text || "No source-supported detailed summary was returned.";

  findingsList.replaceChildren();
  renderFindingGroup(findingsList, "Key takeaways", analysis.key_takeaways);
  renderFindingGroup(findingsList, "Important names, dates, and figures", analysis.important_entities);
  renderFindingGroup(findingsList, "Risks", analysis.risks, "risk-group");
  renderFindingGroup(findingsList, "Decisions", analysis.decisions);
  renderFindingGroup(findingsList, "Action items", analysis.action_items);
  if (!findingsList.childElementCount) appendTextElement(findingsList, "p", "No additional source-supported findings were returned.", "empty-findings");

  dashboardSummaryEmpty.hidden = true;
  dashboardSummaryContent.hidden = false;
  dashboardInsights.replaceChildren();
  renderFindingGroup(dashboardInsights, "Key takeaways", analysis.key_takeaways);
  renderFindingGroup(dashboardInsights, "Important details", analysis.important_entities);
  renderFindingGroup(dashboardInsights, "Risks and actions", [...(analysis.risks || []), ...(analysis.decisions || []), ...(analysis.action_items || [])]);
  insightPlaceholders.hidden = true;
  dashboardInsights.hidden = false;
  insightsEmptyCaption.hidden = true;

  analysisWarnings.replaceChildren();
  if (analysis.warnings?.length) {
    analysisWarnings.hidden = false;
    for (const warning of analysis.warnings) appendTextElement(analysisWarnings, "p", warning, "warning-item");
  } else {
    analysisWarnings.hidden = true;
  }
}

async function runAnalysis() {
  if (!state.documentId || analyzeButton.disabled) return;
  state.analyzing = true;
  deleteDocumentButton.disabled = true;
  newAnalysisButton.disabled = true;
  downloadSummaryButton.disabled = true;
  downloadReportButton.disabled = true;
  analyzeButton.disabled = true;
  analysisError.hidden = true;
  analysisState.hidden = false;
  analysisStateText.textContent = "Analyzing extracted passages with source checks…";
  analysisOutput.hidden = true;
  try {
    const response = await fetch(`/api/v1/documents/${encodeURIComponent(state.documentId)}/analyze`, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `Analysis failed (${response.status}).`);
    renderAnalysis(payload);
  } catch (error) {
    analysisState.hidden = true;
    analysisError.textContent = error.message || "Teddy could not analyze this document. Try again.";
    analysisError.hidden = false;
    analyzeButton.disabled = false;
    fetch(`/api/v1/documents/${encodeURIComponent(state.documentId)}/results`)
      .then((response) => response.ok ? response.json() : null)
      .then((result) => { if (result?.workflow) renderWorkflow(result.workflow); })
      .catch(() => {});
  } finally {
    state.analyzing = false;
    deleteDocumentButton.disabled = false;
    newAnalysisButton.disabled = false;
    downloadReportButton.disabled = false;
    downloadSummaryButton.disabled = !analysisOutput.dataset.ready;
  }
}

function setExportMessage(message, isError = false) {
  downloadStatus.hidden = isError;
  downloadError.hidden = !isError;
  (isError ? downloadError : downloadStatus).textContent = message;
}

function downloadName(response, fallback) {
  const header = response.headers.get("Content-Disposition") || "";
  const match = header.match(/filename="?([^";]+)"?/i);
  return (match?.[1] || fallback).replace(/[\\/\u0000-\u001f]/g, "_").slice(0, 140) || fallback;
}

async function downloadExport(kind, tableIndex = null) {
  const documentId = state.documentId;
  if (!documentId || state.downloading || state.deleting) return;
  if (kind === "summary" && !analysisOutput.dataset.ready) {
    setExportMessage("Generate the document summary before downloading it.", true);
    return;
  }
  const routes = {
    summary: `/api/v1/documents/${encodeURIComponent(documentId)}/export/summary.md`,
    report: `/api/v1/documents/${encodeURIComponent(documentId)}/export/report.pdf`,
    csv: `/api/v1/documents/${encodeURIComponent(documentId)}/export/tables/${tableIndex}.csv`,
  };
  const buttons = [downloadSummaryButton, downloadReportButton, ...document.querySelectorAll(".table-export-button")];
  state.downloading = true;
  buttons.forEach((button) => { button.disabled = true; });
  downloadError.hidden = true;
  downloadStatus.hidden = false;
  downloadStatus.textContent = "Preparing your download…";
  try {
    const response = await fetch(routes[kind]);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Export failed (${response.status}).`);
    }
    const expected = Number(response.headers.get("Content-Length")) || 0;
    const reader = response.body?.getReader();
    const chunks = [];
    let received = 0;
    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        received += value.length;
        downloadStatus.textContent = expected
          ? `Downloading… ${Math.min(100, Math.round(received / expected * 100))}%`
          : `Downloading… ${formatBytes(received)}`;
      }
    } else {
      chunks.push(await response.arrayBuffer());
    }
    if (state.documentId !== documentId) throw new Error("The active document changed before the download completed. Try again.");
    const blob = new Blob(chunks, { type: response.headers.get("Content-Type") || "application/octet-stream" });
    if (!blob.size) throw new Error("Teddy returned an empty export.");
    const fallback = kind === "summary" ? "teddy-summary.md" : kind === "report" ? "teddy-report.pdf" : "teddy-table.csv";
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = downloadName(response, fallback);
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    setExportMessage(`${kind === "csv" ? "CSV" : kind === "report" ? "PDF report" : "Summary"} downloaded successfully.`);
  } catch (error) {
    setExportMessage(error.message || "Teddy could not prepare the download. Please try again.", true);
  } finally {
    state.downloading = false;
    buttons.forEach((button) => { button.disabled = false; });
    downloadSummaryButton.disabled = !analysisOutput.dataset.ready;
  }
}

async function startNewAnalysis() {
  if (state.busy || state.analyzing || state.chatBusy || state.downloading || state.deleting) return;
  const oldDocumentId = state.documentId;
  state.deleting = true;
  deleteDocumentButton.disabled = true;
  newAnalysisButton.disabled = true;
  resetSelection({ deleteStored: false });
  selectionStatus.textContent = "Ready for a new document. Choose a file to begin another analysis.";
  const deleted = await deleteDocument(oldDocumentId);
  selectionStatus.textContent = deleted
    ? "Previous document deleted. Teddy is ready for a new analysis."
    : "Previous document could not be deleted and will expire automatically. Teddy is ready for a new analysis.";
  state.deleting = false;
  deleteDocumentButton.disabled = false;
  newAnalysisButton.disabled = false;
  fileInput.focus();
}

async function deleteActiveDocument() {
  if (!state.documentId || state.deleting || state.downloading || state.busy || state.analyzing || state.chatBusy) return;
  const oldDocumentId = state.documentId;
  state.deleting = true;
  deleteDocumentButton.disabled = true;
  newAnalysisButton.disabled = true;
  setExportMessage("Deleting this document…");
  const deleted = await deleteDocument(oldDocumentId);
  if (deleted) {
    resetSelection({ deleteStored: false });
    selectionStatus.textContent = "Document deleted. Choose another file when you are ready.";
  } else {
    setExportMessage("Teddy could not delete this document. Please retry; it remains available until it expires.", true);
  }
  state.deleting = false;
  deleteDocumentButton.disabled = false;
  newAnalysisButton.disabled = false;
}

function updateUploadProgress(percent, stage) {
  uploadProgress.hidden = false;
  uploadStage.textContent = stage;
  uploadPercent.textContent = percent == null ? "" : `${percent}%`;
  progressFill.style.width = percent == null ? "100%" : `${percent}%`;
}

function sendUpload(file) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/v1/documents/upload");
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        const percentage = Math.min(100, Math.round((event.loaded / event.total) * 100));
        updateUploadProgress(percentage, `Uploading ${file.name}`);
      }
    });
    request.upload.addEventListener("load", () => updateUploadProgress(null, "Upload complete · extracting document…"));
    request.addEventListener("load", () => {
      let response;
      try { response = JSON.parse(request.responseText); } catch { response = {}; }
      if (request.status >= 200 && request.status < 300) resolve(response);
      else reject(new Error(response.detail || `Upload failed (${request.status}).`));
    });
    request.addEventListener("error", () => reject(new Error("Network error. Check your connection and try again.")));
    request.addEventListener("abort", () => reject(new Error("Upload was cancelled.")));
    const body = new FormData();
    body.append("file", file, file.name);
    request.send(body);
  });
}

async function uploadSelectedFile() {
  if (!state.file || state.busy) return;
  setBusy(true);
  clearUploadError();
  uploadProgress.hidden = false;
  updateUploadProgress(null, "Preparing secure upload…");
  try {
    const result = await sendUpload(state.file);
    updateUploadProgress(100, "Extraction complete");
    selectionStatus.textContent = "Text and available tables have been extracted. Select “Analyze with Teddy” to create a source-grounded summary and findings.";
    uploadActions.hidden = true;
    renderResults(result);
  } catch (error) {
    uploadProgress.hidden = true;
    showUploadError(error.message || "The document could not be processed.");
  } finally {
    setBusy(false);
  }
}

async function loadLimits() {
  try {
    const response = await fetch("/api/v1/documents/limits");
    if (response.ok) state.limits = { ...defaultLimits, ...await response.json() };
    document.querySelector(".file-types").textContent = `PDF, DOCX, XLSX, CSV, TXT · up to ${state.limits.max_upload_size_mb} MB`;
    document.querySelector("#upload-size-note").textContent = `Up to ${state.limits.max_upload_size_mb} MB`;
    chatQuestion.maxLength = state.limits.max_chat_question_chars;
    chatLimitNote.textContent = `Questions are limited to ${state.limits.max_chat_question_chars.toLocaleString()} characters. Chat context stays with this document until it expires.`;
  } catch {
    // The server remains authoritative if limits cannot be fetched.
  }
}

browseButton.addEventListener("click", (event) => {
  event.stopPropagation();
  if (!state.busy && !state.analyzing) fileInput.click();
});
dropzone.addEventListener("click", (event) => {
  if (event.target.closest("button") || state.busy || state.analyzing) return;
  fileInput.click();
});
dropzone.addEventListener("keydown", (event) => {
  if ((event.key === "Enter" || event.key === " ") && !state.busy && !state.analyzing) {
    event.preventDefault();
    fileInput.click();
  }
});
fileInput.addEventListener("change", () => selectFile(fileInput.files[0]));
for (const eventName of ["dragenter", "dragover"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    if (!state.busy && !state.analyzing) dropzone.classList.add("is-dragging");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-dragging");
  });
}
dropzone.addEventListener("drop", (event) => selectFile(event.dataTransfer.files[0]));
submitUpload.addEventListener("click", uploadSelectedFile);
removeSelection.addEventListener("click", () => resetSelection());
document.querySelector("#delete-document").addEventListener("click", () => resetSelection());
analyzeButton.addEventListener("click", runAnalysis);
chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendChatQuestion();
});
chatQuestion.addEventListener("input", () => {
  chatSend.disabled = !chatQuestion.value.trim() || state.chatBusy || !state.documentId;
});
chatQuestion.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendChatQuestion();
  }
});
loadLimits();
