# Teddy – Smart AI Analyst

Teddy is a document analysis workspace being built incrementally. It provides a FastAPI application, secure temporary uploads and text/table extraction for PDF, DOCX, TXT, CSV, and XLSX, optional NVIDIA NIM summaries and insights, Python-calculated analytics, and document-specific AI chat with source quotes.

## Requirements

- Python 3.11 or newer
- Windows PowerShell

## Run locally on Windows

From the project root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
python -m uvicorn backend.main:app --reload
```

If PowerShell blocks virtual-environment activation, run this in the current terminal and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

The app will be available at <http://127.0.0.1:8000>. FastAPI's interactive API docs are at <http://127.0.0.1:8000/docs>.

## Run tests

With the virtual environment active, from the project root:

```powershell
python -m pytest
```

The health check is available at <http://127.0.0.1:8000/health> and returns:

```json
{"status":"ok","service":"teddy"}
```

## Optional AI providers

AI is disabled by default: `AI_PROVIDER=none` performs no external AI calls. The application sets `ALLOW_PAID_APIS=false` and does not provide a paid mode, automatic provider fallback, or billing setup. Extraction, local analytics, chat retrieval, citation checks, and supported exports continue to use local application code when AI is unavailable.

NVIDIA NIM can be selected only after you independently confirm genuinely free developer API access for the exact account, endpoint, model, and applicable quota. Configure `AI_PROVIDER=nvidia_nim`, `NVIDIA_NIM_FREE_ACCESS_CONFIRMED=true`, `NVIDIA_API_KEY`, `NVIDIA_MODEL`, and the approved `NVIDIA_BASE_URL`. Keep the key in the backend environment only. A provider/model name, consumer app, or playground is not proof of free API access.

Grok is disabled unless `AI_PROVIDER=grok`, `ENABLE_GROK=true`, `GROK_FREE_API_ACCESS_CONFIRMED=true`, `XAI_API_KEY`, and `XAI_MODEL` are all configured. Enable it only after separately confirming genuinely free API access on the account; consumer Grok access does not qualify.

These confirmation settings are safety gates, not live checks of pricing, account eligibility, or remaining free quota. Free availability is not guaranteed. If access is unavailable or exhausted, AI requests stop with a safe error; there is no silent paid fallback or retry for authentication, rate-limit, quota, billing, or payment-required errors. Never commit `.env` or put credentials in frontend code.

`POST /api/v1/documents/{document_id}/analyze` analyzes the content extracted at upload time; it does not parse the document again. Results are cached in the in-memory document record. AI output is bounded, schema-validated, and checked for source provenance. Matching quotations do not prove logical support, so AI-written interpretations still need human review.

## Data-grounded analytics

Tabular data extracted from CSV, XLSX, and DOCX tables is profiled with Pandas during upload. `GET /api/v1/documents/{document_id}/analytics` returns validated chart specifications, calculated KPI values, comparison tables, timelines, source context, and data-quality warnings. Upload results include the same analytics object. Aggregations are explicit (sum for clearly additive measures such as revenue/quantity, mean for other repeated measures); missing and unparseable values are excluded and reported. Text passages are only profiled when they contain at least three repeated, explicitly labelled numeric lines with a consistent unit. Unlabelled prose numbers do not generate charts.

Chart.js renders the backend-calculated values in the browser. Each chart has a collapsible view of its underlying calculated rows. A chart is omitted when there are too few values, too many categories, mixed units, or no suitable structure. Chart.js is loaded from a pinned CDN release; if that CDN is unavailable, the calculated table data remains visible.

## Document chat

`POST /api/v1/documents/{document_id}/chat` accepts `{"question": "..."}`. Source-aware chunks are prepared once at upload. Chat uses bounded, pure-Python BM25-style lexical retrieval over only that document's extracted content; recent conversation turns for that document can help resolve follow-up questions. Selected evidence is sent to the configured NVIDIA NIM provider, and returned source IDs and exact quotes are checked against the retrieved passages before citations are shown. If retrieval has no relevant passage, or returned citations cannot be verified, Teddy says it could not verify the answer. This checks quote provenance, not whether every model interpretation is correct.

There is no authentication or multi-user ownership system. Random document IDs act as bearer identifiers: anyone who obtains an ID can access that document until it expires or is deleted. This is a single-user/demo limitation, not production-grade tenant isolation. Chat history and extracted content are kept in process memory and are cleared when the process restarts or the document expires. Requests are bounded by `CHAT_MAX_QUESTION_CHARS`, `CHAT_RETRIEVAL_TOP_K`, `CHAT_MAX_CONTEXT_CHARS`, `CHAT_HISTORY_TURNS`, and `CHAT_HISTORY_MAX_CHARS` in `.env.example`.

## Exports

- `GET /api/v1/documents/{document_id}/export/summary.md` downloads the generated summary and its source quotes. It returns `409` until analysis has completed.
- `GET /api/v1/documents/{document_id}/export/report.pdf` creates a PDF report with the filename, available summary and findings, calculated statistics, chart data, and extracted source references. Missing sections are labeled as unavailable; no results are fabricated.
- `GET /api/v1/documents/{document_id}/export/tables/{table_index}.csv` downloads one extracted table. Formula-like cells and headers are escaped for spreadsheet safety.

Each export resolves the requested document ID through the same expiring in-memory store used by chat and results. CSV table indexes are zero-based. PDF output uses ReportLab; AI and source text is escaped before PDF markup rendering.

## Document uploads

- `POST /api/v1/documents/upload` accepts a multipart field named `file` and parses the document during the request.
- `GET /api/v1/documents/{document_id}/status` returns processing metadata.
- `GET /api/v1/documents/{document_id}/results` returns extracted text, tables, references, and warnings.
- `DELETE /api/v1/documents/{document_id}` removes the in-memory record and its temporary source file.
- `GET /api/v1/documents/limits` provides the configured upload limit and supported extensions to the browser.

The default upload limit is 10 MB and can be changed up to 100 MB with `MAX_UPLOAD_SIZE_MB`. The ASGI middleware caps multipart request bodies before parsing, and the upload handler separately caps the file bytes. Document parsing and AI provider calls are bounded to two concurrent tasks by default. Other bounded-processing settings and the temporary directory are documented in `.env.example`. Extracted content and metadata are held in process memory; temporary source files are deleted on request or on expiry cleanup at the next store access. Documents expire after 30 minutes by default. A process restart clears in-memory records, and Render's filesystem is ephemeral. Do not use this storage for durable or multi-instance data.

PDF page references are retained. DOCX paragraphs and tables are emitted in document order where possible. CSV and XLSX responses include columns, rows, and sheet names. Scanned PDF pages return a warning because OCR is not included yet. The upload limit is a resource bound, not a processing-time guarantee.

## Configuration and security

Application settings can be provided as environment variables or in a local `.env` file. `.env` is ignored by Git. NVIDIA NIM credentials are backend-only; never add them to browser code or commit a populated `.env` file. Uploaded document text is treated as untrusted context; chat does not execute instructions, tools, or code from document content.

## Current scope

The frontend displays extracted content, optional source-grounded AI summaries and findings, calculated analytics when supported by actual data, document chat with verified source quotes, and per-document Markdown, PDF, and CSV exports. These features depend on provider configuration and the available extracted content; the application does not invent summary, insight, or chart results when the source does not support them. Supported uploads are PDF, DOCX, TXT, CSV, and XLSX. PowerPoint, legacy XLS, image OCR, persistent storage, authentication, and production-grade tenant isolation are not implemented. `backend/Dockerfile` and `backend/render.yaml` provide deployment configuration scaffolds; no service has been deployed or connected.
