# CREWS: Credit Risk Early Warning System — Architecture

An end-to-end agentic credit risk analysis system built on LangGraph. Given a company and its financial documents, the platform produces a structured credit risk verdict (Red / Amber / Green traffic light) backed by quantitative financial analysis, live external signal retrieval, and an AI-generated analyst narrative — all subject to MAS FEAT-aligned compliance guardrails.

> **Academic prototype:** CREWS was built as a university project and is not a production system or a product of any bank. The compliance disclaimer and guardrails described below (see [Compliance Guardrails](#5-compliance-guardrails)) are designed product features showing how such a tool would be governed inside a lending institution. They are not a usage restriction on this repository.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Subgraph Reference](#2-subgraph-reference)
   - [FIS — Financial Ingestion Subgraph](#fis--financial-ingestion-subgraph)
   - [RS — Retrieval Subgraph](#rs--retrieval-subgraph)
   - [SIS — Signal Sourcing Subgraph](#sis--signal-sourcing-subgraph)
   - [FRD — Fusion & Risk Decisioning Subgraph](#frd--fusion--risk-decisioning-subgraph)
3. [Data Flow & State Schemas](#3-data-flow--state-schemas)
4. [User Flow](#4-user-flow)
5. [Compliance Guardrails](#5-compliance-guardrails)
6. [API Reference](#6-api-reference)
7. [Setup & Running](#7-setup--running)
8. [Project Structure](#8-project-structure)
9. [Design Decisions](#9-design-decisions)

---

## 1. Architecture Overview

```
+---------------------------------------------------------------------+
|                        USER / ANALYST                               |
|                  (Streamlit frontend, port 8501)                    |
+------------------------------+--------------------------------------+
                               | HTTP (REST)
                               v
+---------------------------------------------------------------------+
|                    FastAPI Backend  (port 8000)                     |
|                                                                     |
|  POST /api/cases                -- create case                      |
|  POST /api/cases/{id}/documents -- upload XML/XBRL/PDF             |
|  POST /api/cases/{id}/run-all   -- trigger full pipeline            |
|  GET  /api/cases/{id}/status    -- poll for status                  |
|  GET  /api/cases/{id}/result    -- fetch full results               |
|  POST /api/cases/{id}/chat      -- AI chat assistant                |
|  POST /api/cases/{id}/guidance  -- save analyst guidance            |
|                                                                     |
|  BackgroundTask thread                                              |
|  graph_runner.py  →  run_full_pipeline()                            |
|                                                                     |
|  +---------+    +------+    +------+    +------+                   |
|  |   FIS   |--->|  RS  |--->| SIS  |--->| FRD  |                   |
|  +---------+    +------+    +------+    +------+                   |
|       |              |           |           |                      |
|       +-------- SQLite (CaseState JSON) ------+                     |
+---------------------------------------------------------------------+
                               |
                               v
                    OpenRouter API Gateway
                    (google/gemini-2.5-flash)
                    All 4 subgraphs + chat
```

The pipeline is **stateless between HTTP requests**: all state lives in SQLite as a serialised `CaseState` JSON blob. The frontend polls `/status` every 2 seconds until a terminal status is reached.

---

## 2. Subgraph Reference

### FIS — Financial Ingestion Subgraph

**Purpose:** Extract structured financial data from uploaded documents and compute quantitative risk metrics.

**Technology:** Synchronous LangGraph, OpenRouter (Gemini Flash), PyMuPDF, `xml.etree`.

```
ingest_client_financials
         |
         v
parse_financial_documents      <-- LLM (Gemini Flash via OpenRouter)
         |
         v
extract_financial_features     <-- Deterministic (no LLM)
         |
        END
```

#### Node Details

| Node | What it does |
|------|-------------|
| `ingest_client_financials` | Validates uploaded files exist on disk. Removes missing files, records a warning per missing file. Sets `status = fis_ingestion_complete`. |
| `parse_financial_documents` | PDFs are read via PyMuPDF; XML/XBRL are pre-parsed into a nested dict before the LLM sees them. The LLM returns a fixed JSON schema (IS / BS / CF / period + historical periods). Wrapped in tenacity retry (3 attempts, exponential backoff). Sets `status = fis_parsing_complete`. |
| `extract_financial_features` | Pure deterministic computation: derives working capital, total debt, EBITDA; computes 14 financial ratios; selects the correct Altman Z-Score formula; looks up industry peer benchmarks; computes historical Z-Scores. Sets `status = fis_features_extracted`. |

#### Altman Z-Score Formula Selection

```
Is the company manufacturing?
+-- No  --> Z'' (non-manufacturing, 2000):  6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4'
+-- Yes --> Is it public with a market cap?
            +-- Yes --> Z  (original, 1968):  1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
            +-- No  --> Z' (revised, 1983):   0.717*X1 + 0.847*X2 + 3.107*X3 + 0.420*X4' + 0.998*X5

Where:
  X1 = Working Capital / Total Assets
  X2 = Retained Earnings / Total Assets
  X3 = EBIT / Total Assets
  X4 = Market Cap / Total Liabilities          (original only)
  X4'= Book Equity / Total Liabilities         (revised + non-manufacturing)
  X5 = Revenue / Total Assets                  (original + revised only)
```

**Terminal statuses:** `fis_features_extracted` | `fis_error` | `fis_ingestion_skipped`

---

### RS — Retrieval Subgraph

**Purpose:** Search the web, news, and financial filings for credit-relevant signals about the company, prioritising recent coverage while preserving access to historically significant events (e.g. ongoing litigation).

**Technology:** Async LangGraph, Tavily Search API, OpenRouter (Gemini Flash), asyncio.

```
plan_retrieval              <-- LLM: generate date-anchored queries per topic
        |
        v
execute_searches            <-- Async: parallel Tavily calls
        |
        v
normalize_and_dedup         <-- Deterministic: URL deduplication, field normalisation
        |
        v
relevance_filter            <-- Keyword pre-filter, then LLM (batches of 25): score 0–1, keep >= 0.5
        |
        v
coverage_gate               <-- Policy: are all coverage topics satisfied?
        |
   +----+--------------------+
sufficient               retry (<=2x)      exhausted
   |                         |                |
   v                         v                v
source_quality_          retrieval_retry --> execute_searches (loop)
assessment               (new queries)
   |
  END
```

#### Coverage Topics

The RS graph tracks 8 default topics per company:

1. **governance** — board composition, audit oversight
2. **financials** — revenue, earnings, debt, cash flow
3. **legal_regulatory** — lawsuits, investigations, sanctions
4. **market_position** — competitive landscape, market share
5. **management** — leadership changes, fraud allegations
6. **controversy** — scandals, allegations
7. **competition** — rivals, industry dynamics
8. **environmental** — ESG risks, emissions

The LLM planner can add company- or industry-specific topics on top of these (for example `supply_chain_risk` or `operational_efficiency`).

The `coverage_gate` node checks keyword overlap between retrieved snippets and each topic; a topic is satisfied once it has its minimum number of sources (2 for governance, financials, legal_regulatory, market_position and competition; 1 for management, controversy and environmental). If coverage is insufficient and fewer than 2 retries have been used, `retrieval_retry` generates more targeted queries.

#### Recency Strategy

RS prioritises recent news without hard-dropping historically relevant items:

- **Query anchoring:** Today's date is injected into the LLM user prompt. The system prompt instructs the LLM to append the current year to all non-filing queries (e.g. `"Acme Corp earnings 2025"`), steering search engines toward recent coverage.
- **Score-based prioritisation:** No hard date cutoff. Items are scored with recency weighted at **40%** of total quality score. A 5-year-old Reuters article about an active lawsuit (domain=0.95, recency=0.30, corroboration=0.33 for a single occurrence) still scores about 0.57, above the 0.45 discard threshold.
- **Filing exception:** Financial filings (SEC, EDINET) are not date-filtered at the query level as annual reports publish on yearly cycles.

#### Source Quality Scoring (Deterministic)

`source_quality_assessment` scores each retrieved item on three dimensions:

| Factor | Weight | Details |
|--------|--------|---------|
| Domain reputation | 40% | Reuters/Bloomberg = 0.95, SEC.gov = 0.98, unknown = 0.50 |
| Recency | 40% | ≤30 days = 1.0, ≤90 days = 0.90, ≤1 year = 0.70, ≤2 years = 0.50, older = 0.30 (unknown date = 0.50) |
| Corroboration | 20% | Number of results from the same domain ÷ 3, capped at 1.0 (full score at 3+ results) |

Items scoring below 0.45 are discarded before SIS handoff.

**Terminal statuses:** `rs_complete` | `rs_error`

---

### SIS — Signal Sourcing Subgraph

**Purpose:** Extract, validate, verify, and de-conflict structured credit risk signals from retrieved documents.

**Technology:** Synchronous LangGraph, OpenRouter (Gemini Flash), `concurrent.futures.ThreadPoolExecutor`, sentence-transformers (`all-MiniLM-L6-v2` embeddings, `cross-encoder/nli-deberta-v3-base` NLI).

```
extract                     <-- LLM: identify Signal objects from documents (parallel, 10 workers)
    |
    v
validate                    <-- Deterministic evidence checks (document exists, offsets, snippet)
    |
    v
verify                      <-- LLM grounding verification (parallel, 10 workers)
    |
    v
conflict                    <-- Merge duplicates, embedding pre-filter, NLI screen, LLM confirm
    |
    v
evidence_gate               <-- Routing: frd_direct vs targeted_retrieval
    |
   END
```

#### Node Details

| Node | What it does |
|------|-------------|
| `extract` | Identifies credit-relevant events in each document. Each signal has: `event_type` (from taxonomy), `event_subtype`, `severity` (high/medium/low/positive), `confidence` (0–1), and `evidence` (source snippets with character offsets). |
| `validate` | Checks each signal's evidence: the cited document must exist, character offsets must be non-negative and ordered, and the snippet must be non-empty. Offsets past the end of the text pass with a warning. If more than 30% of a document's signals fail, the document is flagged for re-extraction (max 2 retries) and its failed signals are dropped; the graph currently logs this request rather than re-running extraction. Otherwise failed signals pass through with warnings. |
| `verify` | Calls the LLM in parallel (10 workers) to ground each signal against its source text. Verdict `yes` keeps confidence, `partial` multiplies it by 0.5, `no` by 0.2. Signals left below 0.4 confidence are marked ambiguous at `evidence_gate`. |
| `conflict` | Stage 1 merges cross-document signals with the same `event_subtype`. Stage 1.5 skips cross-document pairs whose snippets have embedding cosine similarity below 0.15. Stage 2 screens the remaining pairs with an NLI cross-encoder, and Stage 3 asks the LLM (10 workers) to confirm candidate contradictions. A confirmed contradiction between two sources that both have quality ≥ 0.8 marks both signals `disputed` and ambiguous; otherwise the higher-quality source wins and the other signal is merged into it. Positive signals are also marked ambiguous when another document carries a high-severity negative signal. |
| `evidence_gate` | Deterministic, and drops nothing: every signal goes to FRD (`frd_direct`). Disputed signals, weak ones (confidence < 0.4 or no evidence) and moderate ones (0.4–0.7, or resolved conflicts) are marked ambiguous; confidence ≥ 0.7 and not already ambiguous stays clear. Non-disputed high-severity signals below 0.5 confidence also produce a targeted-retrieval request, which is logged only because the loop back to RS is not wired yet. |

**Terminal statuses:** `sis_complete` | `sis_error` | `sis_skipped_no_docs`

---

### FRD — Fusion & Risk Decisioning Subgraph

**Purpose:** Combine SIS signals with FIS financial metrics into a final traffic-light credit verdict and compliance-compliant analyst report.

**Technology:** Synchronous LangGraph, OpenRouter (Gemini Flash).

```
aggregate_inputs            <-- Merge SIS signals + FIS financial profile
        |
        v
score_risk                  <-- Deterministic: evaluate 12 binary criteria
        |
        v
generate_report             <-- LLM: 8-section compliance-compliant analyst narrative
        |
       END
```

#### Scoring Logic

`score_risk` evaluates 12 binary criteria organised by weight:

**Category A — Signal-driven (8 criteria)**

Signals with confidence below 0.5 are ignored for every Category A criterion.

| ID | Weight | Criteria |
|----|--------|----------|
| A1 | HIGH | Any high-severity, non-ambiguous financial distress signal |
| A2 | HIGH | 2+ legal/regulatory signals of high or medium severity |
| A3 | MEDIUM | 2+ management/governance signals |
| A4 | MEDIUM | 2+ operational issue signals of high or medium severity |
| A5 | LOW | 2+ reputation/sentiment signals of high or medium severity |
| A6 | LOW | Any market/industry risk signal |
| A7 | LOW | Any disputed signal |
| A8 | MITIGATING | Any non-ambiguous positive signal (see mitigation rule below) |

**Category B — Financial (4 criteria, requires FIS data)**

| ID | Weight | Criteria |
|----|--------|----------|
| B1 | HIGH | Z-Score in the distress zone |
| B2 | MEDIUM | Z-Score in the grey zone (only checked when B1 is not met) |
| B3 | MEDIUM | Z-Score declining 2+ consecutive years |
| B4 | MEDIUM | Approximate peer percentile rank below 25. The rank is the company's linear position (0–100) between its industry's benchmark distress and safe Z-Scores, not a true peer distribution |

Zone cut-offs depend on the Z-Score variant: original Z distress < 1.81, safe ≥ 2.99; revised Z' distress < 1.23, safe ≥ 2.90; non-manufacturing Z'' distress < 1.10, safe ≥ 2.60.

**Traffic Light Decision Rules**

```
RED   if: >= 2 HIGH criteria met
      or: >= 3 MEDIUM criteria met

AMBER if: exactly 1 HIGH criterion met
      or: >= 1 MEDIUM criterion met
      or: >= 3 LOW criteria met

GREEN otherwise

Mitigation: if A8 is met and the non-ambiguous positive signals have an
average confidence >= 0.65:
  RED   -> AMBER  if <= 2 HIGH criteria were met
  AMBER -> GREEN
```

The traffic light is **deterministic and auditable** — you can re-run scoring with different `ScoringConfig` thresholds without invoking any LLM.

#### Report Generation

`generate_report` prompts the LLM to write an 8-section analyst report in JSON:

1. `executive_summary` — traffic light, primary reasons, recommended stance
2. `key_risk_findings` — 3–5 bullet points ordered by severity
3. `financial_health_assessment` — Z-Score zone, trend, peer context
4. `signal_details` — per-category signal themes and evidence
5. `disputed_and_ambiguous` — signals requiring analyst attention
6. `data_quality_notes` — source staleness, coverage gaps
7. `recommended_actions` — 2–3 concrete next steps for the analyst
8. `disclaimer` — mandatory verbatim MAS FEAT compliance statement (cannot be modified by the LLM)

The LLM is explicitly prohibited from overriding the traffic light verdict or making investment recommendations.

**Terminal statuses:** `frd_complete` | `frd_error` | `frd_skipped_no_sis`

---

## 3. Data Flow & State Schemas

The pipeline uses **two separate state schemas** because FIS/RS and SIS/FRD were designed around different LangGraph patterns:

```
+--------------------------------------------------------------------+
|  AgentWorkerState  (TypedDict — FIS and RS)                        |
|                                                                    |
|  case: CaseState          <- central Pydantic model, persisted     |
|                              to SQLite as JSON after every stage   |
|  _rs_coverage             <- CoverageState dict, RS-internal       |
+--------------------------------------------------------------------+
                |
                |  frd_bridge.py converts between schemas
                v
+--------------------------------------------------------------------+
|  PipelineState  (TypedDict, total=False — SIS and FRD)             |
|                                                                    |
|  company_id, documents        <- from CaseState.normalized_docs    |
|  extraction/validation/...    <- SIS intermediate state            |
|  sis_output                   <- written by SIS, read by FRD       |
|  financial_profile            <- from CaseState.financial_features |
|  frd_aggregated, risk_score,  <- FRD intermediate + output         |
|  frd_output                                                        |
+--------------------------------------------------------------------+
                |
                |  graph_runner.py writes back frd_output + sis_output
                v
+--------------------------------------------------------------------+
|  CaseState  (Pydantic BaseModel — single source of truth in DB)    |
|                                                                    |
|  company: CompanyProfile                                           |
|  uploaded_financial_documents: list[UploadedFinancialDocument]     |
|  parsed_financial_documents:   list[ParsedFinancialDocument]       |
|  financial_features:           FinancialFeatures   <- FIS output   |
|  retrieval_plan:               list[RetrievalQuery]                |
|  raw_retrieval_results:        list[RawRetrievedItem]              |
|  normalized_documents:         list[DocumentInput]  <- RS output   |
|  coverage:                     CoverageStatus                      |
|  sis_output:                   dict | None           <- SIS output  |
|  frd_output:                   dict | None           <- FRD output  |
|  frd_traffic_light:            str | None            <- cached      |
|  analyst_guidance:             str | None                          |
|  status, warnings, errors, audit_log                               |
+--------------------------------------------------------------------+
```

### Status Progression

```
created
  --> fis_running
        --> fis_ingestion_complete --> fis_parsing_complete
              --> fis_features_extracted
                --> rs_running --> rs_plan_complete --> rs_searches_complete
                      --> rs_normalized --> rs_filtered
                            --> rs_coverage_sufficient | rs_coverage_retry | rs_coverage_exhausted
                                  --> rs_complete
                                        --> sis_running --> sis_complete | sis_skipped_no_docs
                                              --> frd_running --> frd_complete | frd_skipped_no_sis

Error states at any stage: fis_error | rs_error | sis_error | frd_error
```

---

## 4. User Flow

### Step-by-Step

**Step 1 — Case Entry**
- Navigate to **Case Entry**
- Enter company name, entity type (private/public), industry sector, and jurisdiction
- An intake compliance notice is shown before the form — read it before proceeding
- Click **Initialize Assessment** — you receive a `case_id` stored in session state
- Upload financial documents (XML, XBRL, or PDF) in the Supporting Documents section below the form
- At least one document is required to run FIS

**Step 2 — Run Analysis**
- Navigate to **Run Analysis**
- Optionally enter **Special Instructions** (e.g. "Focus on liquidity risk and the pending SEC investigation") — these are injected as analyst guidance into the FRD report prompt
- Click **▶ Run Full Pipeline** to run all four subgraphs in sequence
- Or run individual stages with the FIS / RS / SIS / FRD buttons
- A progress bar appears above the Audit Trail section and updates every 2 seconds
- The pipeline progress circle (top right) shows stages completed out of 4
- The Audit Trail terminal updates live with node-level events as the pipeline runs

**Step 3 — Results Dashboard**
- Navigate to **Results Dashboard**
- The page opens with a compliance banner — all outputs are preliminary and require analyst review
- Review sections:
  1. **Traffic Light Verdict** — Red/Amber/Green with criteria scorecard
  2. **Quantitative Assessment** — Z-Score, zone, formula, components, peer comparison
  3. **Financial Ratios** — liquidity, leverage, profitability, efficiency
  4. **LLM Analysis Highlights** — top risk signals extracted by SIS with severity and evidence
  5. **Analyst Report** — AI-generated 8-section narrative (expandable, downloadable)
  6. **Credit Intelligence Assistant** — chat interface for follow-up questions
- Download the full result as JSON for offline use or audit trail

---

## 5. Compliance Guardrails

The system implements MAS FEAT-aligned guardrails at two independent layers.

### LLM Prompt Layer (backend)

**Chat assistant (`backend/services/chat_service.py`):**
The LLM system prompt contains mandatory compliance constraints that cannot be overridden by user messages:
- Must not provide investment advice, buy/sell/hold recommendations, or credit rating predictions
- Must not recommend specific financial instruments or credit actions
- Must caveat all creditworthiness claims as preliminary AI-generated analysis subject to human review
- Must decline requests for investment advice and redirect to a qualified professional
- Must flag data gaps and low-confidence signals as limitations

**Report generation (`orchestration/frd/prompts/report_template.py`):**
- Explicitly prohibited from making investment recommendations or formal credit rating statements
- Must qualify all AI-derived findings with language such as "based on available data" or "subject to analyst verification"
- Required to include a mandatory verbatim `disclaimer` field as a JSON key in every generated report — the LLM cannot modify or omit it

### Disclaimer Text (verbatim, in every report)

> *"This report was generated by an AI system and is intended solely for internal credit risk assessment by authorised personnel of the lending institution. It does not constitute investment advice, a formal credit rating, or a regulatory determination. All findings are preliminary and subject to human review and sign-off before use in any credit decision. Model outputs may reflect data gaps, retrieval errors, or hallucination. MAS FEAT principles (Fairness, Ethics, Accountability, Transparency) apply."*

### Regulatory References

- **MAS FEAT Principles** — Fairness, Ethics, Accountability, Transparency for AI in financial services
- **MAS Notice on AI/ML Model Risk Management** — model governance requirements for financial AI
- **MAS Guidelines on Financial Advisory Services** — AI tools cannot provide regulated financial advice without a licence

---

## 6. API Reference

All endpoints are prefixed with `/api`. Interactive docs at `http://localhost:8000/docs`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/cases` | Create a new case. |
| `GET` | `/cases` | List all cases (most recent first, limit 50). |
| `GET` | `/cases/{id}/status` | Lightweight status poll. Returns `frd_traffic_light`. |
| `GET` | `/cases/{id}/result` | Full `CaseState` as JSON. |
| `POST` | `/cases/{id}/documents` | Upload a financial document (multipart/form-data). |
| `POST` | `/cases/{id}/guidance` | Save analyst special instructions. |
| `POST` | `/cases/{id}/chat` | Send a message to the AI assistant for this case. |
| `POST` | `/cases/{id}/run-fis` | Start FIS as a background task. |
| `POST` | `/cases/{id}/run-rs` | Start RS as a background task. |
| `POST` | `/cases/{id}/run-sis` | Start SIS as a background task. |
| `POST` | `/cases/{id}/run-frd` | Start FRD. `?skip_report=true` omits LLM narrative. |
| `POST` | `/cases/{id}/run-all` | Run FIS → RS → SIS → FRD sequentially. |
| `GET` | `/health` | Returns `{"status": "healthy"}`. |

### CreateCaseRequest

```json
{
  "company_name": "Acme Corp",
  "company_type": "private",
  "jurisdiction": "United States",
  "industry_sector": "manufacturing"
}
```

### CaseStatusResponse

```json
{
  "case_id": "case-a1b2c3d4",
  "status": "frd_complete",
  "company_name": "Acme Corp",
  "warnings": [],
  "errors": [],
  "created_at": "2026-04-06T10:00:00",
  "updated_at": "2026-04-06T10:05:32",
  "audit_log_count": 18,
  "frd_traffic_light": "amber"
}
```

### ChatRequest / ChatResponse

```json
// Request
{ "message": "What are the top liquidity risks?", "history": [] }

// Response
{ "reply": "Based on available data, the key liquidity risk indicators are…" }
```

---

## 7. Setup & Running

### Prerequisites

- Python 3.11+
- API keys:
  - **OpenRouter** (`OPENROUTER_API_KEY`) — all LLM calls (FIS, RS, SIS, FRD, chat)
  - **Tavily** (`TAVILY_API_KEY`) — RS web retrieval

### Installation

```bash
cd crews-credit-risk-early-warning

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

### Environment Variables

Copy `.env.example` to `.env` in the project root and fill it in (never commit `.env`):

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL_ID=google/gemini-2.5-flash
TAVILY_API_KEY=tvly-...
DATABASE_URL=sqlite:///./data/crews.db

# Optional: override model per stage
# OPENROUTER_MODEL_FIS=google/gemini-2.0-flash
# OPENROUTER_MODEL_RS=google/gemini-2.0-flash
# OPENROUTER_MODEL_SIS=google/gemini-2.5-flash
# OPENROUTER_MODEL_FRD=google/gemini-2.5-pro
```

### Running (Windows — recommended)

Double-click `start.bat` or run it from the terminal. It opens two command windows — one for the backend and one for the frontend.

```
Backend:  http://localhost:8000
Frontend: http://localhost:8501
```

### Running (macOS / Linux)

```bash
cp .env.example .env          # then fill in the API keys
./start.sh                    # backend + frontend; Ctrl+C stops both
```

### Running (manual)

```bash
# Terminal 1 — Backend
.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000 --reload      # Windows
.venv/bin/python -m uvicorn backend.main:app --port 8000 --reload              # macOS / Linux

# Terminal 2 — Frontend
.venv\Scripts\python.exe -m streamlit run frontend\app\main.py                 # Windows
.venv/bin/python -m streamlit run frontend/app/main.py                         # macOS / Linux
```

---

## 8. Project Structure

```
crews-credit-risk-early-warning/
│
├── start.bat                      # Launch backend + frontend in one click
├── .env                           # API keys — NEVER commit this file
├── .streamlit/
│   └── config.toml                # Streamlit theme (textColor, primaryColor, etc.)
│
├── backend/
│   ├── main.py                    # FastAPI app, CORS middleware, lifespan
│   ├── api/routes/cases.py        # All API endpoints + request/response schemas
│   └── services/
│       ├── graph_runner.py        # Background task runners: run_fis/rs/sis/frd_graph()
│       ├── chat_service.py        # AI chat assistant with compliance guardrails
│       └── db/
│           ├── session.py         # SQLAlchemy engine, get_db(), init_db()
│           ├── models.py          # CaseRecord ORM model
│           └── crud.py            # create/get/update/list_cases operations
│
├── orchestration/
│   ├── state.py                   # AgentWorkerState + PipelineState TypedDicts
│   ├── graph.py                   # Top-level SIS → FRD combined graph
│   ├── fis/
│   │   ├── graph.py               # build_fis_graph()
│   │   └── nodes.py               # ingest / parse / extract_features nodes
│   ├── rs/
│   │   ├── graph.py               # build_rs_graph() with conditional retry loop
│   │   ├── nodes.py               # plan/execute/normalize/filter/gate/retry/quality nodes
│   │   ├── coverage.py            # CoverageState, 8 default coverage topics
│   │   └── prompts.py             # LLM prompts for query planning and relevance scoring
│   ├── sis/
│   │   ├── graph.py               # build_sis_graph()
│   │   └── nodes/
│   │       ├── extract.py         # Signal extraction (LLM)
│   │       ├── validate.py        # Pydantic schema validation
│   │       ├── verify.py          # Grounding verification (parallel LLM, 10 workers)
│   │       ├── conflict.py        # Contradiction detection and resolution (NLI + LLM)
│   │       └── evidence_gate.py   # Routing: frd_direct vs targeted_retrieval
│   └── frd/
│       ├── graph.py               # build_frd_graph()
│       ├── nodes/
│       │   ├── aggregate_inputs.py  # Merge SIS + FIS into unified dict
│       │   ├── score_risk.py        # Deterministic 12-criteria scoring → TrafficLight
│       │   └── generate_report.py   # LLM 8-section analyst narrative
│       └── prompts/
│           └── report_template.py   # Report system prompt with compliance hard rules
│
├── shared/
│   ├── config.py                  # Settings (loads .env with override=True)
│   ├── llm.py                     # OpenRouter client factory (sync + async)
│   ├── taxonomy.py                # EventCategory, Severity enums
│   ├── schemas/
│   │   ├── documents.py           # DocumentInput (RS → SIS handoff schema)
│   │   ├── signals.py             # Signal, Evidence, SISOutput schemas
│   │   └── frd.py                 # FinancialProfile, RiskScore, FRDOutput, TrafficLight
│   └── states/
│       ├── case_state.py          # CaseState + all nested models
│       ├── zscore.py              # Deterministic Z-Score, ratio, EBITDA computation
│       ├── industry_benchmarks.py # Static sector benchmark table
│       └── frd_bridge.py          # Schema converters: CaseState ↔ PipelineState
│
├── frontend/
│   └── app/
│       ├── main.py                # Streamlit entry point, CSS design system, page router
│       └── pages/
│           ├── case_entry.py      # Case creation form + document upload
│           ├── run_analysis.py    # Pipeline execution, live audit trail, polling
│           └── results.py         # Traffic light, signals, report, AI chat
│
└── data/
    ├── uploads/                   # Uploaded financial documents (per-case subdirectory)
    └── crews.db                   # SQLite database (auto-created on first run)
```

---

## 9. Design Decisions

### Why deterministic scoring in FRD?

The traffic light verdict is the highest-stakes output. Deterministic rule-based scoring makes decisions auditable and reproducible — you can re-run scoring with different `ScoringConfig` thresholds without re-invoking any LLM. The LLM is used only for the advisory narrative report. This also aligns with MAS model risk governance requirements for explainability.

### Why no hard date cutoffs in RS?

An ongoing lawsuit, regulatory investigation, or credit event may have originated years ago but remain materially relevant to current creditworthiness. Hard cutoffs would silently drop this evidence. Instead, recency is handled via scoring (40% weight with a decay curve) so recent items rank higher without old-but-relevant items being discarded.

### Why two state schemas?

`AgentWorkerState` (TypedDict wrapping a Pydantic `CaseState`) was designed for FIS/RS, which needed a rich, persisted, evolving model with named reducers. `PipelineState` (flat TypedDict, `total=False`) was designed for SIS/FRD, which process documents in a single pass. Rather than refactoring either, `frd_bridge.py` converts between them at the graph boundary.

### Why SQLite with a single JSON blob?

All of `CaseState` is stored as a single JSON `TEXT` column. This avoids schema migrations when adding fields — just add a field with a default value. The tradeoff is that SQL cannot filter on nested fields. For a prototype this is the right tradeoff; production would use PostgreSQL with JSONB.

### Why OpenRouter for all LLM calls?

OpenRouter provides a single OpenAI-compatible API endpoint that routes to any model. This means model selection is entirely configuration-driven via environment variables (`OPENROUTER_MODEL_FIS`, `OPENROUTER_MODEL_FRD`, etc.) — no code changes required to switch models. All four subgraphs and the chat assistant use the same client pattern from `shared/llm.py`.

### Why async LangGraph for RS but sync for the others?

RS fires multiple Tavily search queries in parallel (the planner generates at least 2 queries per coverage topic, spread across source types). LangGraph's async `ainvoke` path supports this naturally with `asyncio.gather`. FIS, SIS, and FRD are sequential single-threaded pipelines; the concurrency in SIS (10 workers each for the extract, verify and conflict LLM calls) is handled inside the node functions using `ThreadPoolExecutor`, not at the graph level.
