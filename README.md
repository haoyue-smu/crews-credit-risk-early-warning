# UBS Agentic Credit Assessment Platform

An end-to-end agentic credit risk analysis system built on LangGraph. Given a company and its financial documents, the platform produces a structured credit risk verdict (Red / Amber / Green traffic light) backed by quantitative financial analysis, live external signal retrieval, and an AI-generated analyst narrative.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Subgraph Reference](#2-subgraph-reference)
   - [FIS — Financial Ingestion Subgraph](#fis--financial-ingestion-subgraph)
   - [RS — Retrieval Subgraph](#rs--retrieval-subgraph)
   - [SIS — Signal Intelligence Subgraph](#sis--signal-intelligence-subgraph)
   - [FRD — Fusion & Risk Decisioning Subgraph](#frd--fusion--risk-decisioning-subgraph)
3. [Data Flow & State Schemas](#3-data-flow--state-schemas)
4. [User Flow](#4-user-flow)
5. [API Reference](#5-api-reference)
6. [Setup & Running](#6-setup--running)
7. [Project Structure](#7-project-structure)
8. [Design Decisions](#8-design-decisions)

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
|  POST /api/cases             -- create case                         |
|  POST /api/cases/{id}/documents -- upload XML/XBRL/PDF              |
|  POST /api/cases/{id}/run-all   -- trigger full pipeline            |
|  GET  /api/cases/{id}/status    -- poll for status                  |
|  GET  /api/cases/{id}/result    -- fetch full results               |
|                                                                     |
|  BackgroundTask thread                                              |
|  graph_runner.py                                                    |
|  run_full_pipeline()                                                |
|       |                                                             |
|       v                                                             |
|  +---------+    +------+    +------+    +------+                   |
|  |   FIS   |--->|  RS  |--->| SIS  |--->| FRD  |                   |
|  +---------+    +------+    +------+    +------+                   |
|       |              |           |           |                      |
|       +-------- SQLite (CaseState JSON) ------+                     |
+---------------------------------------------------------------------+
```

The pipeline is **stateless between HTTP requests**: all state lives in SQLite as a serialized `CaseState` JSON blob. The frontend polls `/status` every 2 seconds until a terminal status is reached.

---

## 2. Subgraph Reference

### FIS — Financial Ingestion Subgraph

**Purpose:** Extract structured financial data from uploaded documents and compute quantitative risk metrics.

**Technology:** Synchronous LangGraph, OpenRouter (Gemini Flash via OpenAI SDK), PyMuPDF, `xml.etree`.

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
| `ingest_client_financials` | Validates that uploaded files exist on disk. Removes missing files, records a warning per missing file. Sets `status = fis_ingestion_complete`. |
| `parse_financial_documents` | For each document: PDFs are read via PyMuPDF; XML/XBRL are deterministically pre-parsed into a nested dict to give the LLM structure rather than raw markup. The LLM returns a fixed JSON schema (IS / BS / CF / period + historical periods). Wrapped in tenacity retry (3 attempts, exponential backoff). Sets `status = fis_parsing_complete`. |
| `extract_financial_features` | Pure deterministic computation: (1) derives working capital, total debt, EBITDA; (2) computes 14 financial ratios; (3) selects the correct Altman Z-Score formula and computes the score; (4) looks up industry peer benchmarks; (5) computes historical Z-Scores from `historical_periods`. Sets `status = fis_features_extracted`. |

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

**Purpose:** Search the web, news, and financial filings for credit-relevant signals about the company.

**Technology:** Async LangGraph, Tavily Search API, OpenRouter (Gemini Flash), asyncio.

```
plan_retrieval              <-- LLM: generate search queries per topic
        |
        v
execute_searches            <-- Async: parallel Tavily calls
        |
        v
normalize_and_dedup         <-- Deterministic: URL hashing, field normalization
        |
        v
relevance_filter            <-- LLM (batches of 25): score each item 0-1, keep >= 0.3
        |
        v
coverage_gate               <-- Policy check: are all 8 topics covered?
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

1. **financials** — revenue, earnings, debt, cash flow
2. **legal_regulatory** — lawsuits, investigations, sanctions
3. **management** — leadership changes, fraud allegations
4. **market_position** — competitive landscape, market share
5. **credit_events** — downgrades, defaults, restructuring
6. **macro_factors** — industry trends, economic headwinds
7. **esg** — environmental, social, governance risks
8. **operational** — supply chain, production, cyber incidents

The `coverage_gate` node checks keyword overlap between retrieved snippets and each topic. If coverage is insufficient and fewer than 2 retries have been used, `retrieval_retry` generates more targeted queries.

#### Source Quality Scoring (Deterministic)

`source_quality_assessment` scores each retrieved item on three dimensions:

- **Domain reputation** — tiered list: Reuters/Bloomberg (0.95), Forbes/FT (0.90), unknown (0.4)
- **Recency** — items from the last 30 days score 1.0; older items decay linearly to 0.5
- **Corroboration** — items whose domain appears 3+ times in results get a 20% boost

**Terminal statuses:** `rs_complete` | `rs_error`

---

### SIS — Signal Intelligence Subgraph

**Purpose:** Extract, validate, verify, and de-conflict structured credit risk signals from retrieved documents.

**Technology:** Synchronous LangGraph, Google Gemini SDK (direct), LangExtract, DeBERTa NLI model, `concurrent.futures.ThreadPoolExecutor`.

```
extract                     <-- LangExtract + Gemini: extract Signal objects
    |
    v
validate                    <-- Pydantic schema validation + completeness checks
    |
    v
verify                      <-- Gemini grounding verification (parallel, 10 workers)
    |
    v
conflict                    <-- DeBERTa NLI + Gemini: detect and resolve contradictions
    |
    v
evidence_gate               <-- Routing rules: frd_direct vs targeted_retrieval
    |
   END
```

#### Node Details

| Node | What it does |
|------|-------------|
| `extract` | Uses LangExtract with Gemini to identify credit-relevant events in each document. Each signal has: `event_type` (from taxonomy), `event_subtype`, `severity` (high/medium/low/positive), `confidence` (0–1), and `evidence` (source snippets with character offsets). |
| `validate` | Runs Pydantic model validation against the `Signal` schema. Checks required fields, confidence range, char interval ordering. Signals failing hard validation are discarded; those with minor issues pass with warnings. |
| `verify` | Calls Gemini grounding API in parallel (10 workers) for each signal. Grounding either confirms the signal with a source URL or marks it ambiguous. Confidence is adjusted based on the grounding verdict. |
| `conflict` | Groups signals by `event_type` and uses DeBERTa NLI to detect contradictory pairs (e.g., "company expanding" vs "company laying off"). Contradictions are sent to Gemini for resolution. Uses a Disjoint Set Union structure to track resolved groups. |
| `evidence_gate` | Applies deterministic routing rules: high-confidence, no-conflict signals go `frd_direct`; low-confidence or disputed signals are routed to `targeted_retrieval` (future RS feedback loop). |

**Terminal statuses:** `sis_complete` | `sis_error` | `sis_skipped_no_docs`

---

### FRD — Fusion & Risk Decisioning Subgraph

**Purpose:** Combine SIS signals with FIS financial metrics into a final traffic-light credit verdict and analyst report.

**Technology:** Synchronous LangGraph, Google Gemini SDK (direct, for report), deterministic scoring.

```
aggregate_inputs            <-- Merge SIS signals + FIS financial profile
        |
        v
score_risk                  <-- Deterministic: evaluate 12 binary criteria
        |
        v
generate_report             <-- LLM (Gemini): 7-section analyst narrative
        |
       END
```

#### Scoring Logic

`score_risk` evaluates 12 binary criteria organized by weight:

**Category A — Signal-driven (8 criteria)**

| ID | Weight | Criteria |
|----|--------|----------|
| A1 | HIGH | Any `payment_default` or `debt_restructuring` signal present |
| A2 | HIGH | Any `fraud` or `accounting_irregularity` signal present |
| A3 | MEDIUM | 2+ `legal_regulatory` signals |
| A4 | MEDIUM | Any `credit_rating_downgrade` signal |
| A5 | MEDIUM | 3+ high-severity signals of any type |
| A6 | LOW | Any management or governance concern signal |
| A7 | LOW | Any ESG risk signal |
| A8 | LOW | 2+ `operational_risk` signals |

**Category B — Financial (4 criteria, requires FIS data)**

| ID | Weight | Criteria |
|----|--------|----------|
| B1 | HIGH | Z-Score in distress zone |
| B2 | MEDIUM | Z-Score in grey zone |
| B3 | MEDIUM | Z-Score declining for 2+ consecutive years |
| B4 | LOW | Z-Score below industry peer median |

**Traffic Light Decision Rules (configurable via `ScoringConfig`)**

```
RED   if: >= 1 HIGH criteria met
      or: >= 3 MEDIUM criteria met

AMBER if: >= 1 MEDIUM criteria met
      or: >= 3 LOW criteria met

GREEN otherwise

Mitigating factors (positive signals with confidence >= 0.7) can downgrade
RED -> AMBER only if <= 1 HIGH criteria were met.
```

#### Report Generation

`generate_report` asks Gemini to write a 7-section analyst report:

1. Executive Summary
2. Financial Health Analysis (Z-Score, ratios)
3. Market & Competitive Position
4. Risk Factors Identified
5. Mitigating Factors
6. Peer Comparison
7. Recommendation & Forward Outlook

**Terminal statuses:** `frd_complete` | `frd_error` | `frd_skipped_no_sis`

---

## 3. Data Flow & State Schemas

The pipeline uses **two separate state schemas** because FIS/RS and SIS/FRD were designed around different LangGraph patterns:

```
+--------------------------------------------------------------------+
|  AgentWorkerState  (TypedDict -- FIS and RS)                       |
|                                                                    |
|  case: CaseState          <- central Pydantic model, persisted to  |
|                              SQLite as JSON after every stage      |
|  retrieved_items_buffer   <- list[RawRetrievedItem], reducer: add  |
|  _rs_coverage             <- CoverageState dict, RS-internal        |
+--------------------------------------------------------------------+
                |
                |  graph_runner.py uses frd_bridge.py to convert
                v
+--------------------------------------------------------------------+
|  PipelineState  (TypedDict, total=False -- SIS and FRD)            |
|                                                                    |
|  company_id, documents        <- from CaseState.normalized_docs   |
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
|  CaseState  (Pydantic BaseModel -- single source of truth in DB)   |
|                                                                    |
|  company: CompanyProfile                                           |
|  uploaded_financial_documents: list[UploadedFinancialDocument]     |
|  parsed_financial_documents:   list[ParsedFinancialDocument]       |
|  financial_features:           FinancialFeatures   <- FIS output  |
|  retrieval_plan:               list[RetrievalQuery]                |
|  raw_retrieval_results:        list[RawRetrievedItem]              |
|  normalized_documents:         list[DocumentInput]  <- RS output  |
|  coverage:                     CoverageStatus                      |
|  sis_output:                   dict | None           <- SIS output |
|  frd_output:                   dict | None           <- FRD output |
|  frd_traffic_light:            str | None            <- cached     |
|  status, warnings, errors, audit_log                               |
+--------------------------------------------------------------------+
```

### Status Progression

```
created
  --> fis_running --> fis_ingestion_complete --> fis_parsing_complete
    --> fis_features_extracted
      --> rs_running --> rs_coverage_sufficient | rs_coverage_exhausted
        --> rs_complete
          --> sis_running --> sis_complete | sis_skipped_no_docs
            --> frd_running --> frd_complete | frd_skipped_no_sis

Error states at any stage: fis_error | rs_error | sis_error | frd_error
```

---

## 4. User Flow

### End-to-End Flow (Happy Path)

```
Analyst                 Streamlit UI         FastAPI          SQLite
  |                          |                   |               |
  |-- Open app ------------>|                   |               |
  |                          |                   |               |
  |-- Fill company form --->|                   |               |
  |   (name, type, sector)   |-- POST /cases -->|               |
  |                          |                   |-- INSERT ---->|
  |                          |<-- {case_id} -----|               |
  |                          |                   |               |
  |-- Upload XML/PDF ------->|                   |               |
  |                          |-- POST /docs ---->|               |
  |                          |                   |-- save file   |
  |                          |<-- {doc_id} ------|-- UPDATE ---->|
  |                          |                   |               |
  |-- Click "Run Pipeline" ->|                   |               |
  |                          |-- POST /run-all ->|               |
  |                          |                   |- BackgroundTask
  |                          |<-- {started} -----|   |           |
  |  (polling every 2s)      |                   |   v           |
  |                          |-- GET /status --->|  FIS graph    |
  |                          |<- {fis_running} --|   |           |
  |                          |-- GET /status --->|   v           |
  |                          |<- {rs_running} ---|  RS graph     |
  |                          |-- GET /status --->|   |           |
  |                          |<- {sis_running} --|   v           |
  |                          |-- GET /status --->|  SIS graph    |
  |                          |<- {frd_running} --|   |           |
  |                          |-- GET /status --->|   v           |
  |                          |<- {frd_complete} -|  FRD graph    |
  |                          |   + traffic_light |               |
  |                          |                   |               |
  |-- Navigate to Results -->|                   |               |
  |                          |-- GET /result --->|               |
  |                          |                   |-- SELECT ---->|
  |                          |<-- full CaseState-|<-- JSON ------|
  |                          |                   |               |
  |<-- Z-Score, signals,     |                   |               |
  |    traffic light, report-|                   |               |
```

### Step-by-Step User Instructions

**Step 1 — Create Case**
- Navigate to **Create Case** in the sidebar
- Enter company name, select type (public/private), choose industry sector
- For public companies: optionally enter market cap (required for the original 1968 Z-Score formula)
- Click **Create** — you receive a `case_id` stored in session state

**Step 2 — Upload Documents**
- Navigate to **Upload Documents**
- Upload one or more financial statements (XML, XBRL, or PDF)
- At least one document is required before running FIS

**Step 3 — Run Analysis**
- Navigate to **Run Analysis**
- Click **Run Full Pipeline** to run all four subgraphs in sequence
- Or run individual stages with the FIS / RS / SIS / FRD buttons
- Watch the status badge update in real-time (polls every 2 seconds)
- The traffic light appears in the status bar as soon as FRD completes

**Step 4 — Review Results**
- Navigate to **Results**
- Review sections in order:
  1. **Z-Score** — score, zone, formula used, components, historical trend, peer comparison
  2. **Financial Ratios** — liquidity, leverage, profitability, efficiency
  3. **Financial Statements** — IS / BS / CF raw numbers (tabbed)
  4. **Retrieval Results** — sources found by RS with quality scores
  5. **SIS Signals** — extracted risk signals with severity, confidence, conflict status
  6. **FRD Traffic Light** — Red/Amber/Green verdict with criteria scorecard
  7. **Analyst Report** — full AI-generated narrative (expandable)
- Download the full result as JSON for offline use or audit

---

## 5. API Reference

All endpoints are prefixed with `/api`. Interactive docs at `http://localhost:8000/docs`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/cases` | Create a new case. |
| `GET` | `/cases` | List all cases (most recent first, limit 50). |
| `GET` | `/cases/{id}/status` | Lightweight status poll. Returns `frd_traffic_light`. |
| `GET` | `/cases/{id}/result` | Full `CaseState` as JSON. |
| `POST` | `/cases/{id}/documents` | Upload a financial document (multipart/form-data). |
| `POST` | `/cases/{id}/run-fis` | Start FIS as a background task. |
| `POST` | `/cases/{id}/run-rs` | Start RS as a background task. |
| `POST` | `/cases/{id}/run-sis` | Start SIS as a background task. |
| `POST` | `/cases/{id}/run-frd` | Start FRD. `?skip_report=true` omits LLM narrative. |
| `POST` | `/cases/{id}/run-all` | Run FIS -> RS -> SIS -> FRD sequentially. |
| `GET` | `/health` | Returns `{"status": "healthy"}`. |

### CreateCaseRequest body

```json
{
  "company_name": "Acme Corp",
  "company_type": "private",
  "jurisdiction": "US",
  "industry_sector": "manufacturing",
  "is_manufacturing": true,
  "market_cap": null
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
  "created_at": "2026-04-01T10:00:00",
  "updated_at": "2026-04-01T10:05:32",
  "audit_log_count": 14,
  "frd_traffic_light": "amber"
}
```

---

## 6. Setup & Running

### Prerequisites

- Python 3.11+
- API keys:
  - **OpenRouter** (`OPENROUTER_API_KEY`) — FIS parsing + RS relevance filter
  - **Tavily** (`TAVILY_API_KEY`) — RS web retrieval
  - **Gemini** (`GEMINI_API_KEY`) — SIS verification + FRD report generation

### Installation

```bash
cd ubs_credit_assessment_smu

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root (never commit this):

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL_ID=google/gemini-2.5-flash
TAVILY_API_KEY=tvly-...
GEMINI_API_KEY=AIza...

# Optional: override default SQLite with PostgreSQL
# DATABASE_URL=postgresql://user:pass@localhost/ubs_credit
```

### Run the Backend

```bash
python -m uvicorn backend.main:app --port 8000 --reload
```

### Run the Frontend

```bash
python -m streamlit run frontend/app/main.py
```

### Smoke-Test Graph Compilation

```bash
python -m orchestration.runner
```

Expected output:
```
Compiling FIS graph...  OK
Compiling RS graph...   OK
Compiling SIS graph...  OK
Compiling FRD graph...  OK

All four subgraphs compiled successfully.
```

---

## 7. Project Structure

```
ubs_credit_assessment_smu/
|
+-- backend/
|   +-- main.py                    # FastAPI app entry point, CORS, lifespan
|   +-- api/routes/cases.py        # All 10 API endpoints + request/response schemas
|   +-- services/
|       +-- graph_runner.py        # Background task runners: run_fis/rs/sis/frd_graph()
|       +-- db/
|           +-- session.py         # SQLAlchemy engine, get_db(), init_db()
|           +-- models.py          # CaseRecord, UploadedFileRecord ORM models
|           +-- crud.py            # create/get/update/list operations
|
+-- orchestration/
|   +-- state.py                   # AgentWorkerState + PipelineState TypedDicts
|   +-- runner.py                  # Smoke-test: compiles all 4 subgraphs
|   +-- fis/
|   |   +-- graph.py               # build_fis_graph()
|   |   +-- nodes.py               # ingest / parse / extract_features nodes
|   +-- rs/
|   |   +-- graph.py               # build_rs_graph() with conditional retry loop
|   |   +-- nodes.py               # plan/execute/normalize/filter/gate/retry/quality
|   |   +-- coverage.py            # CoverageState, topic keyword matching
|   |   +-- prompts.py             # System prompts for RS LLM calls
|   +-- sis/
|   |   +-- graph.py               # build_sis_graph() + node wrapper functions
|   |   +-- nodes/
|   |       +-- extract.py         # parallel_extract_signals (LangExtract + Gemini)
|   |       +-- validate.py        # schema_validation_gate (Pydantic)
|   |       +-- verify.py          # parallel_verify_signals (Gemini grounding, 10 workers)
|   |       +-- conflict.py        # conflict_resolution (DeBERTa NLI + Gemini + DSU)
|   |       +-- evidence_gate.py   # evidence routing rules
|   +-- frd/
|       +-- graph.py               # build_frd_graph()
|       +-- nodes/
|           +-- aggregate_inputs.py  # Merge SIS + FIS into unified dict
|           +-- score_risk.py        # Deterministic 12-criteria scoring -> TrafficLight
|           +-- generate_report.py  # Gemini 7-section analyst narrative
|
+-- shared/
|   +-- config.py                  # Settings (loads .env), require_llm/retrieval/gemini()
|   +-- taxonomy.py                # EventCategory, Severity enums
|   +-- schemas/
|   |   +-- documents.py           # DocumentInput (RS -> SIS handoff schema)
|   |   +-- signals.py             # Signal, Evidence, SISOutput, SISMetadata
|   |   +-- frd.py                 # FinancialProfile, RiskScore, FRDOutput, TrafficLight
|   |   +-- retrieval.py           # TargetedRetrievalRequest (future RS feedback loop)
|   +-- states/
|       +-- case_state.py          # CaseState + all nested models (CompanyProfile, etc.)
|       +-- zscore.py              # Deterministic Z-Score, ratio, EBITDA computation
|       +-- industry_benchmarks.py # Static sector benchmark table + get_benchmark()
|       +-- frd_bridge.py          # Schema converters: CaseState <-> PipelineState
|
+-- frontend/
|   +-- app/
|       +-- main.py                # Streamlit app entry point + page router
|       +-- pages/
|           +-- create_case.py
|           +-- upload_documents.py
|           +-- run_analysis.py    # Status polling + FIS/RS/SIS/FRD action buttons
|           +-- results.py         # Z-Score, ratios, signals, traffic light, report
|
+-- data/
|   +-- uploads/                   # Uploaded financial documents (per case subdirectory)
|   +-- ubs_credit.db              # SQLite database (auto-created on first run)
|
+-- dummy_financials.xml           # Sample XML financial document for testing
+-- requirements.txt
+-- .env                           # API keys -- NEVER commit this file
```

---

## 8. Design Decisions

### Why two state schemas?

`AgentWorkerState` (TypedDict wrapping a Pydantic `CaseState`) was designed for FIS/RS, which needed a rich, persisted, evolving model with named reducers. `PipelineState` (flat TypedDict, `total=False`) was designed for SIS/FRD, which process documents in a single pass and don't need to persist intermediate state. Rather than refactoring either, `frd_bridge.py` converts between them at the graph boundary.

### Why SQLite with a single JSON blob?

All of `CaseState` is stored as a single JSON `TEXT` column. This avoids schema migrations when adding fields — just add the field with a default value. The tradeoff is that SQL queries cannot filter on nested fields (e.g., "all cases with Z-Score < 2.0"). For a prototype context this is the right tradeoff; production would use PostgreSQL with JSONB or a normalized schema.

### Why synchronous LangGraph for FIS/SIS/FRD but async for RS?

RS fires multiple Tavily search queries in parallel (one per coverage topic). LangGraph's async `ainvoke` path supports this naturally with `asyncio.gather`. FIS, SIS, and FRD are all sequential single-threaded pipelines; the concurrency in SIS (10 verify workers) is handled inside node functions using `ThreadPoolExecutor`, not at the graph level.

### Why OpenRouter for FIS/RS but Gemini SDK directly for SIS/FRD?

FIS and RS were built first using the OpenAI SDK against OpenRouter as a model-agnostic gateway. SIS and FRD use Gemini-specific features (grounding API, LangExtract's Gemini integration) that are easier to access via the native `google-genai` SDK. Both ultimately route to Gemini Flash models.

### Why deterministic scoring in FRD?

The traffic light verdict is the highest-stakes output. Deterministic rule-based scoring makes decisions auditable and reproducible — you can re-run scoring with different `ScoringConfig` thresholds without re-invoking any LLM. The LLM is used only for the advisory narrative report.
