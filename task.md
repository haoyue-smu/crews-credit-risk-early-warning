# Task Tracker — FIS + RS Build

## Phase 1: Schema & Computation Foundations
- [x] Update `shared/states/case_state.py` — rich FinancialFeatures, Z-Score models, CompanyProfile industry fields
- [x] New `shared/states/zscore.py` — deterministic ratio + Altman Z-Score computation (all 3 variants)
- [x] New `shared/states/industry_benchmarks.py` — static peer comparison by industry sector
- [x] Update `dummy_financials.xml` — richer test data (IS + BS + CF)
- [x] Update `requirements.txt` + `.env`

## Phase 2: FIS Node Fixes & Enhancements
- [x] Fix `parse_financial_documents` — PyMuPDF for PDF, lxml for XML/XBRL, json_object LLM extract
- [x] Fix `extract_financial_features` — deterministic: build FinancialFeatures, compute ratios, Z-score, peer compare, audit log
- [x] Fix `model_copy(deep=True)` everywhere
- [x] Add `tenacity` retry on LLM calls
- [x] Emit `AuditEvent` from all FIS nodes
- [x] Update `fis/graph.py` 

## Phase 3: Retrieval Subgraph (RS)
- [x] New `orchestration/rs/__init__.py`
- [x] New `orchestration/rs/coverage.py` — dynamic coverage topic system
- [x] New `orchestration/rs/prompts.py` — retrieval planning prompt templates  
- [x] New `orchestration/rs/nodes.py` — plan_retrieval, search_*, parallel_fetch, normalize, filter, coverage_gate, retry
- [x] New `orchestration/rs/graph.py` — async RS LangGraph with Send map-reduce

## Phase 4: FastAPI Backend
- [x] Update `backend/services/db/models.py` — CaseRecord + UploadedFile SQLAlchemy models
- [x] Update `backend/services/db/session.py` — SQLite engine + `get_db` dep
- [x] Update `backend/services/db/crud.py` — CRUD helpers
- [x] New `backend/services/graph_runner.py` — async graph runner + SQLite callback
- [x] New `backend/api/routes/cases.py` — case management endpoints
- [x] Update `backend/main.py` — CORS, lifespan, new routes

## Phase 5: Streamlit Frontend
- [x] New `frontend/app/main.py` — entry point
- [x] New `frontend/app/pages/create_case.py`
- [x] New `frontend/app/pages/upload_documents.py`
- [x] New `frontend/app/pages/run_analysis.py`
- [x] New `frontend/app/pages/results.py`
