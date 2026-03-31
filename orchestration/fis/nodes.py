import base64
import os
import json
from typing import Any, Dict

from openai import OpenAI

from shared.config import settings
from shared.states.case_state import (
    UploadedFinancialDocument,
    ParsedFinancialDocument,
    FinancialFeatures,
)
from orchestration.state import AgentWorkerState


def get_openrouter_client():
    """Initializes the OpenRouter client using the OpenAI SDK."""
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key or "DUMMY_KEY_IF_MISSING",
    )


def ingest_client_financials(state: AgentWorkerState) -> Dict[str, Any]:
    """
    Node 1 (FIS): Validates and prepares uploaded financial documents for processing.
    Ensures that the case state has 'uploaded_financial_documents' populated.
    """
    print(f"--- [FIS] INGEST CLIENT FINANCIALS ---")
    case = state["case"]
    
    if not case.uploaded_financial_documents:
        print("No documents found to ingest. Skipping FIS parsing.")
        return {"case": case}
    
    print(f"Ingested {len(case.uploaded_financial_documents)} documents.")
    
    case_copy = case.model_copy()
    case_copy.status = "fis_ingestion_complete"
    return {"case": case_copy}


def _read_file_as_base64_data_uri(filepath: str, file_type: str) -> str:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    with open(filepath, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
        
    mime = "application/pdf" if file_type == "pdf" else "text/plain"
    return f"data:{mime};base64,{encoded}"


def _read_file_as_text(filepath: str) -> str:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def parse_financial_documents(state: AgentWorkerState) -> Dict[str, Any]:
    """
    Node 2 (FIS): Iterates over uploaded docs and uses OpenRouter (Gemini) to extract structured raw statements.
    Works for PDF, XML, and XBRL.
    """
    print(f"--- [FIS] PARSE FINANCIAL DOCUMENTS ---")
    case = state["case"]
    client = get_openrouter_client()
    model_id = settings.openrouter_model_id  # Should be e.g., 'google/gemini-2.5-flash' on OpenRouter

    parsed_docs = []
    
    for doc in case.uploaded_financial_documents:
        print(f"Parsing document: {doc.filename} ({doc.file_type})")
        
        system_instructions = (
            "You are an expert financial analyst. Your task is to extract "
            "the raw financial statements (Income Statement, Balance Sheet, Cash Flow) "
            "into a structured JSON dictionary. If this is XML/XBRL, parse the tags. "
            "If it's PDF, extract the tables."
        )

        try:
            # For Gemini on OpenRouter, we can pass text for XML/XBRL, 
            # and standard Image/Base64 URL blocks for PDF if supported, 
            # though some models require pure text. We will assume the model can handle it.
            if doc.file_type == "pdf":
                file_uri = _read_file_as_base64_data_uri(doc.local_path, doc.file_type)
                content = [
                    {"type": "text", "text": "Extract the core financial statements into JSON."},
                    {"type": "image_url", "image_url": {"url": file_uri}}
                ]
            else:
                file_text = _read_file_as_text(doc.local_path)
                content = f"Here is the raw {doc.file_type.upper()} file:\n\n{file_text}\n\nExtract financial statements into JSON."

            response = client.chat.completions.create(
                model=model_id,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": content}
                ]
            )

            raw_dict = json.loads(response.choices[0].message.content)
            
            parsed_doc = ParsedFinancialDocument(
                document_id=doc.document_id,
                parser_name="openrouter_parser",
                raw_statements=raw_dict
            )
            parsed_docs.append(parsed_doc)

        except Exception as e:
            print(f"Error parsing {doc.filename}: {e}")
            parsed_docs.append(
                ParsedFinancialDocument(
                    document_id=doc.document_id,
                    parser_name="openrouter_error",
                    warnings=[f"Failed to parse with OpenRouter: {str(e)}"]
                )
            )

    case_copy = case.model_copy()
    case_copy.parsed_financial_documents.extend(parsed_docs)
    case_copy.status = "fis_parsing_complete"
    
    return {"case": case_copy}


def extract_financial_features(state: AgentWorkerState) -> Dict[str, Any]:
    """
    Node 3 (FIS): Synthesizes parsed raw statements into uniform FinancialFeatures (ratios, key values) via OpenRouter.
    """
    print(f"--- [FIS] EXTRACT FINANCIAL FEATURES ---")
    case = state["case"]
    client = get_openrouter_client()
    model_id = settings.openrouter_model_id

    if not case.parsed_financial_documents:
        print("No parsed documents available. Skipping feature extraction.")
        return {"case": case}

    aggregated_context = ""
    for p_doc in case.parsed_financial_documents:
        aggregated_context += f"\n--- Document {p_doc.document_id} ---\n"
        aggregated_context += json.dumps(p_doc.raw_statements, indent=2)

    prompt = (
        "You are a credit risk structurer. Look at the raw financial capabilities below "
        "and calculate standard financial features (e.g. Total Revenue, EBITDA, Debt) "
        "and ratios (e.g. Current Ratio, Debt-to-Equity).\n\n"
        f"Raw Financials:\n{aggregated_context}"
    )

    try:
        # Utilize OpenAI SDK's native Parse capability for Structured Outputs via OpenRouter
        response = client.beta.chat.completions.parse(
            model=model_id,
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format=FinancialFeatures,
        )
        
        extracted_features = response.choices[0].message.parsed
        
    except Exception as e:
        print(f"Feature extraction failed: {e}")
        extracted_features = FinancialFeatures(warnings=[f"Feature extraction failed: {str(e)}"])

    case_copy = case.model_copy()
    case_copy.financial_features = extracted_features
    case_copy.status = "fis_features_extracted"

    return {"case": case_copy}
