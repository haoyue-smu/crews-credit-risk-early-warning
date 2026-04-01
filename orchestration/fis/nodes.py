"""Financial Ingestion Subgraph (FIS) — Node implementations.

Three sequential nodes:
  1. ingest_client_financials  — validate uploaded docs exist
  2. parse_financial_documents — extract raw financials via deterministic pre-parse + LLM
  3. extract_financial_features — deterministic: compute ratios, Z-Score, peer comparison

Key fixes over v1:
  - PyMuPDF for PDF text extraction (not base64 image_url)
  - lxml deterministic pre-parse for XML/XBRL before LLM
  - Dropped .beta.parse() — uses json_object + manual Pydantic validation
  - model_copy(deep=True) everywhere
  - AuditEvent emission on every node
  - tenacity retry on LLM calls
  - Deterministic ratio + Z-Score computation post-LLM extraction
"""

import json
import os
import traceback
from datetime import datetime
from typing import Any, Dict
from xml.etree import ElementTree

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from shared.llm import get_client, MODEL_FIS
from shared.states.case_state import (
    AuditEvent,
    BalanceSheetMetrics,
    CashFlowMetrics,
    FinancialFeatures,
    FinancialPeriod,
    IncomeStatementMetrics,
    ParsedFinancialDocument,
    UploadedFinancialDocument,
)
from shared.states.zscore import (
    compute_derived_values,
    compute_ebitda,
    compute_ratios,
    compute_z_score,
    build_peer_comparison,
)
from orchestration.state import AgentWorkerState


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def _audit(node_name: str, event: str, details: dict | None = None) -> AuditEvent:
    return AuditEvent(
        timestamp=datetime.utcnow(),
        node_name=node_name,
        event=event,
        details=details or {},
    )


# ---------------------------------------------------------------------------
# File reading helpers
# ---------------------------------------------------------------------------

def _read_pdf_as_text(filepath: str) -> str:
    """Extract text from PDF using PyMuPDF (fitz)."""
    import fitz  # PyMuPDF

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    doc = fitz.open(filepath)
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        if text.strip():
            pages.append(f"--- Page {page_num + 1} ---\n{text}")
    doc.close()

    if not pages:
        raise ValueError(f"PDF has no extractable text: {filepath}")

    return "\n\n".join(pages)


def _read_file_as_text(filepath: str) -> str:
    """Read a text file (XML, XBRL) as a string."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _deterministic_xml_preparse(xml_text: str) -> dict[str, Any]:
    """Deterministic pre-parse of XML/XBRL to extract tag:value pairs.

    Recursively walks the XML tree and extracts leaf text values,
    producing a nested dict. This gives the LLM structured context
    rather than raw markup, making extraction more reliable.
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return {"_parse_error": "Could not parse as valid XML"}

    def _walk(elem: ElementTree.Element) -> Any:
        # Strip namespace prefixes for cleaner keys
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

        children = list(elem)
        if not children:
            # Leaf node — try to parse as number
            text = (elem.text or "").strip()
            try:
                if "." in text:
                    return float(text)
                return int(text)
            except (ValueError, TypeError):
                return text if text else None

        # Branch node — recurse
        result: dict[str, Any] = {}

        # Capture attributes (e.g. fiscalYear="2024")
        if elem.attrib:
            result["_attributes"] = dict(elem.attrib)

        for child in children:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            child_val = _walk(child)
            if child_tag in result:
                # Handle duplicate tags by converting to list
                existing = result[child_tag]
                if isinstance(existing, list):
                    existing.append(child_val)
                else:
                    result[child_tag] = [existing, child_val]
            else:
                result[child_tag] = child_val
        return result

    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    return {root_tag: _walk(root)}


# ---------------------------------------------------------------------------
# LLM call with retry
# ---------------------------------------------------------------------------

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((Exception,)),
    reraise=True,
)
def _llm_json_call(client: OpenAI, model_id: str, system: str, user: str) -> dict:
    """Make an LLM call expecting a JSON response. Retries up to 3 times."""
    response = client.chat.completions.create(
        model=model_id,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = response.choices[0].message.content
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Node 1: Ingest Client Financials
# ---------------------------------------------------------------------------

def ingest_client_financials(state: AgentWorkerState) -> Dict[str, Any]:
    """Validates uploaded financial documents exist and are readable."""
    print("--- [FIS] INGEST CLIENT FINANCIALS ---")
    case = state["case"].model_copy(deep=True)

    audit_events = []

    if not case.uploaded_financial_documents:
        msg = "No documents found to ingest."
        print(msg)
        case.warnings.append(msg)
        audit_events.append(_audit("ingest_client_financials", "no_documents"))
        case.status = "fis_ingestion_skipped"
        case.audit_log.extend(audit_events)
        return {"case": case}

    validated = []
    for doc in case.uploaded_financial_documents:
        if not os.path.exists(doc.local_path):
            msg = f"File not found: {doc.local_path} ({doc.filename})"
            print(f"  WARNING: {msg}")
            case.warnings.append(msg)
            audit_events.append(_audit("ingest_client_financials", "file_missing", {"filename": doc.filename}))
        else:
            validated.append(doc)
            audit_events.append(_audit(
                "ingest_client_financials", "file_validated",
                {"filename": doc.filename, "file_type": doc.file_type, "size_bytes": os.path.getsize(doc.local_path)},
            ))

    print(f"  Validated {len(validated)}/{len(case.uploaded_financial_documents)} documents.")
    case.uploaded_financial_documents = validated
    case.status = "fis_ingestion_complete"
    case.updated_at = datetime.utcnow()
    case.audit_log.extend(audit_events)

    return {"case": case}


# ---------------------------------------------------------------------------
# Node 2: Parse Financial Documents
# ---------------------------------------------------------------------------

_PARSE_SYSTEM_PROMPT = """\
You are an expert financial data extraction system. Your task is to extract
the core financial statements from the provided document into a structured JSON.

Return a JSON object with exactly these top-level keys (use null for missing data):
{
  "period": {
    "fiscal_year": <int or null>,
    "fiscal_period": "<FY|Q1|Q2|Q3|Q4 or null>",
    "currency": "<ISO currency code or null>",
    "is_audited": <true|false|null>
  },
  "income_statement": {
    "revenue": <float or null>,
    "cost_of_goods_sold": <float or null>,
    "gross_profit": <float or null>,
    "operating_expenses": <float or null>,
    "operating_income": <float or null>,
    "interest_expense": <float or null>,
    "depreciation_amortization": <float or null>,
    "ebitda": <float or null>,
    "net_income": <float or null>,
    "eps": <float or null>
  },
  "balance_sheet": {
    "total_assets": <float or null>,
    "current_assets": <float or null>,
    "cash_and_equivalents": <float or null>,
    "inventory": <float or null>,
    "accounts_receivable": <float or null>,
    "total_liabilities": <float or null>,
    "current_liabilities": <float or null>,
    "long_term_debt": <float or null>,
    "total_debt": <float or null>,
    "total_equity": <float or null>,
    "retained_earnings": <float or null>,
    "working_capital": <float or null>
  },
  "cash_flow": {
    "operating_cash_flow": <float or null>,
    "investing_cash_flow": <float or null>,
    "financing_cash_flow": <float or null>,
    "capital_expenditures": <float or null>,
    "free_cash_flow": <float or null>
  },
  "historical_periods": [
    {
      "fiscal_year": <int>,
      "period_label": "<e.g. FY2022>",
      "income_statement": { ... same shape ... },
      "balance_sheet": { ... same shape ... }
    }
  ]
}

Rules:
- All monetary values should be in the document's native currency as raw numbers (no formatting).
- If historical/comparative data exists in the document, extract each period into historical_periods.
- If a field is not present in the document, set it to null.
- Do NOT fabricate values. Only extract what is explicitly stated or directly computable.
"""


def parse_financial_documents(state: AgentWorkerState) -> Dict[str, Any]:
    """Iterates over uploaded docs, deterministically pre-parses XML/XBRL,
    then uses OpenRouter (Gemini Flash) to extract structured financial data."""
    print("--- [FIS] PARSE FINANCIAL DOCUMENTS ---")
    case = state["case"].model_copy(deep=True)
    client = get_client()
    model_id = MODEL_FIS

    parsed_docs: list[ParsedFinancialDocument] = []
    audit_events = []

    for doc in case.uploaded_financial_documents:
        print(f"  Parsing: {doc.filename} ({doc.file_type})")
        audit_events.append(_audit("parse_financial_documents", "parsing_started", {"filename": doc.filename}))

        try:
            # --- Step 1: Read file content ---
            if doc.file_type == "pdf":
                file_text = _read_pdf_as_text(doc.local_path)
                user_content = (
                    f"Here is the extracted text from a PDF financial report:\n\n"
                    f"{file_text}\n\n"
                    f"Extract the financial statements into the JSON format specified."
                )
            else:
                # XML or XBRL — deterministic pre-parse first
                raw_text = _read_file_as_text(doc.local_path)
                pre_parsed = _deterministic_xml_preparse(raw_text)

                user_content = (
                    f"Here is a pre-parsed {doc.file_type.upper()} financial document.\n\n"
                    f"Pre-parsed structure:\n{json.dumps(pre_parsed, indent=2)}\n\n"
                    f"Raw {doc.file_type.upper()}:\n{raw_text}\n\n"
                    f"Extract the financial statements into the JSON format specified."
                )

            # --- Step 2: LLM extraction ---
            raw_dict = _llm_json_call(client, model_id, _PARSE_SYSTEM_PROMPT, user_content)

            # --- Step 3: Build ParsedFinancialDocument ---
            period_data = raw_dict.get("period", {})
            parsed_doc = ParsedFinancialDocument(
                document_id=doc.document_id,
                parser_name="fis_openrouter_v2",
                fiscal_year=period_data.get("fiscal_year"),
                fiscal_period=period_data.get("fiscal_period"),
                currency=period_data.get("currency"),
                raw_statements=raw_dict,
            )
            parsed_docs.append(parsed_doc)

            audit_events.append(_audit(
                "parse_financial_documents", "parsing_complete",
                {"filename": doc.filename, "fiscal_year": parsed_doc.fiscal_year},
            ))

        except Exception as e:
            tb = traceback.format_exc()
            print(f"  ERROR parsing {doc.filename}: {e}")
            parsed_docs.append(ParsedFinancialDocument(
                document_id=doc.document_id,
                parser_name="fis_openrouter_error",
                warnings=[f"Failed to parse: {str(e)}"],
            ))
            audit_events.append(_audit(
                "parse_financial_documents", "parsing_error",
                {"filename": doc.filename, "error": str(e), "traceback": tb},
            ))

    case.parsed_financial_documents.extend(parsed_docs)
    case.status = "fis_parsing_complete"
    case.updated_at = datetime.utcnow()
    case.audit_log.extend(audit_events)

    return {"case": case}


# ---------------------------------------------------------------------------
# Node 3: Extract Financial Features (Deterministic)
# ---------------------------------------------------------------------------

def extract_financial_features(state: AgentWorkerState) -> Dict[str, Any]:
    """Deterministically builds FinancialFeatures from parsed statements.

    Steps:
      1. Hydrate IS/BS/CF Pydantic models from LLM-extracted raw_statements
      2. Compute derived values (working_capital, total_debt, EBITDA)
      3. Compute all financial ratios
      4. Compute Altman Z-Score (auto-selects formula)
      5. Build peer comparison from static benchmarks
      6. Process historical periods for Z-Score history
    """
    print("--- [FIS] EXTRACT FINANCIAL FEATURES ---")
    case = state["case"].model_copy(deep=True)
    audit_events = []

    if not case.parsed_financial_documents:
        msg = "No parsed documents available. Skipping feature extraction."
        print(f"  {msg}")
        case.warnings.append(msg)
        audit_events.append(_audit("extract_financial_features", "skipped_no_data"))
        case.audit_log.extend(audit_events)
        return {"case": case}

    warnings: list[str] = []

    # Use the first successfully parsed document as the primary source
    primary_doc = None
    for p_doc in case.parsed_financial_documents:
        if p_doc.raw_statements and "fis_openrouter_error" not in p_doc.parser_name:
            primary_doc = p_doc
            break

    if primary_doc is None:
        msg = "All documents failed to parse. Cannot extract features."
        print(f"  {msg}")
        case.warnings.append(msg)
        case.financial_features = FinancialFeatures(warnings=[msg])
        audit_events.append(_audit("extract_financial_features", "all_docs_failed"))
        case.audit_log.extend(audit_events)
        return {"case": case}

    raw = primary_doc.raw_statements
    audit_events.append(_audit(
        "extract_financial_features", "using_primary_doc",
        {"document_id": primary_doc.document_id, "fiscal_year": primary_doc.fiscal_year},
    ))

    # --- Step 1: Hydrate structured metrics from raw LLM output ---
    try:
        is_data = raw.get("income_statement", {})
        bs_data = raw.get("balance_sheet", {})
        cf_data = raw.get("cash_flow", {})
        period_data = raw.get("period", {})

        is_metrics = IncomeStatementMetrics(**{
            k: v for k, v in is_data.items() if k in IncomeStatementMetrics.model_fields
        })
        bs_metrics = BalanceSheetMetrics(**{
            k: v for k, v in bs_data.items() if k in BalanceSheetMetrics.model_fields
        })
        cf_metrics = CashFlowMetrics(**{
            k: v for k, v in cf_data.items() if k in CashFlowMetrics.model_fields
        })
        period = FinancialPeriod(**{
            k: v for k, v in period_data.items() if k in FinancialPeriod.model_fields
        })
    except Exception as e:
        msg = f"Error hydrating metrics from raw statements: {e}"
        warnings.append(msg)
        print(f"  {msg}")
        is_metrics = IncomeStatementMetrics()
        bs_metrics = BalanceSheetMetrics()
        cf_metrics = CashFlowMetrics()
        period = FinancialPeriod()

    # --- Step 2: Compute derived values ---
    working_capital, total_debt = compute_derived_values(bs_metrics, is_metrics)
    if bs_metrics.working_capital is None and working_capital is not None:
        bs_metrics.working_capital = working_capital
    if bs_metrics.total_debt is None and total_debt is not None:
        bs_metrics.total_debt = total_debt

    ebitda = compute_ebitda(is_metrics)
    if is_metrics.ebitda is None and ebitda is not None:
        is_metrics.ebitda = ebitda

    # --- Step 3: Compute ratios ---
    ratios = compute_ratios(bs_metrics, is_metrics, cf_metrics, working_capital, total_debt, ebitda)

    # --- Step 4: Compute current Z-Score ---
    company = case.company
    current_z = compute_z_score(
        bs=bs_metrics,
        is_=is_metrics,
        company_type=company.company_type,
        is_manufacturing=company.is_manufacturing,
        market_cap=company.market_cap,
        fiscal_year=period.fiscal_year or primary_doc.fiscal_year,
        period_label=f"FY{period.fiscal_year or primary_doc.fiscal_year or '?'}",
        working_capital=working_capital,
        total_debt=total_debt,
    )

    audit_events.append(_audit(
        "extract_financial_features", "z_score_computed",
        {
            "score": current_z.score,
            "zone": current_z.zone.value,
            "formula": current_z.formula_used.value,
        },
    ))

    # --- Step 5: Peer comparison ---
    peer = build_peer_comparison(
        industry_sector=company.industry_sector,
        formula_used=current_z.formula_used,
    )

    # --- Step 6: Historical Z-Scores ---
    historical_z: list = []
    hist_periods = raw.get("historical_periods", [])
    for hp in hist_periods:
        try:
            h_is = IncomeStatementMetrics(**{
                k: v for k, v in hp.get("income_statement", {}).items()
                if k in IncomeStatementMetrics.model_fields
            })
            h_bs = BalanceSheetMetrics(**{
                k: v for k, v in hp.get("balance_sheet", {}).items()
                if k in BalanceSheetMetrics.model_fields
            })
            h_wc, h_td = compute_derived_values(h_bs, h_is)
            h_z = compute_z_score(
                bs=h_bs,
                is_=h_is,
                company_type=company.company_type,
                is_manufacturing=company.is_manufacturing,
                market_cap=company.market_cap,
                fiscal_year=hp.get("fiscal_year"),
                period_label=hp.get("period_label", f"FY{hp.get('fiscal_year', '?')}"),
                working_capital=h_wc,
                total_debt=h_td,
            )
            historical_z.append(h_z)
        except Exception as e:
            warnings.append(f"Historical period parse error: {e}")

    if historical_z:
        audit_events.append(_audit(
            "extract_financial_features", "historical_z_scores",
            {"count": len(historical_z), "years": [z.fiscal_year for z in historical_z]},
        ))

    # --- Assemble FinancialFeatures ---
    features = FinancialFeatures(
        period=period,
        income_statement=is_metrics,
        balance_sheet=bs_metrics,
        cash_flow=cf_metrics,
        ratios=ratios,
        current_z_score=current_z,
        historical_z_scores=historical_z,
        peer_comparison=peer,
        warnings=warnings,
    )

    case.financial_features = features
    case.status = "fis_features_extracted"
    case.updated_at = datetime.utcnow()
    case.audit_log.extend(audit_events)

    print(f"  Z-Score: {current_z.score} ({current_z.zone.value} zone, {current_z.formula_used.value})")
    print(f"  Ratios computed: {sum(1 for v in ratios.model_dump().values() if v is not None and not isinstance(v, list))} fields")
    print(f"  Historical Z-Scores: {len(historical_z)} periods")

    return {"case": case}
