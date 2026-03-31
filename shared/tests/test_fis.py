import os
from datetime import datetime
from dotenv import load_dotenv

from shared.states.case_state import CaseState, CompanyProfile, UploadedFinancialDocument
from orchestration.fis.graph import build_fis_graph

# Make sure .env is loaded so OPENROUTER_API_KEY is available
load_dotenv()

def create_dummy_xml():
    """Generates a simple dummy financial XML file for testing purposes."""
    filepath = "dummy_financials.xml"
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0" encoding="UTF-8"?>
<IncomeStatement>
    <Revenue>5000000</Revenue>
    <CostOfGoodsSold>2000000</CostOfGoodsSold>
    <GrossProfit>3000000</GrossProfit>
    <OperatingExpenses>1000000</OperatingExpenses>
    <NetIncome>2000000</NetIncome>
</IncomeStatement>
""")
    return filepath

def test_fis():
    print("1. Assembling Mock Case State...")
    dummy_file = create_dummy_xml()
    
    # Setup dummy case matching our Pydantic schema
    case = CaseState(
        case_id="case-123",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        company=CompanyProfile(
            company_id="comp-1",
            company_name="Test Corp",
            company_type="private"
        ),
        uploaded_financial_documents=[
            UploadedFinancialDocument(
                document_id="doc-1",
                filename="dummy_financials.xml",
                file_type="xml",
                local_path=dummy_file,
                uploaded_at=datetime.utcnow(),
                document_role="annual_report"
            )
        ]
    )

    print("2. Compiling FIS Graph...")
    graph = build_fis_graph()

    print("3. Invoking Graph (Calling OpenRouter)...")
    try:
        # We pass the CaseState wrapped in the AgentWorkerState TypedDict
        final_state = graph.invoke({"case": case})
        
        updated_case: CaseState = final_state["case"]
        
        print("\n--- RESULTS ---")
        print(f"Final Status: {updated_case.status}")
        
        print("\n[Parsed Statements]:")
        for parsed in updated_case.parsed_financial_documents:
            print(f"Parser: {parsed.parser_name}")
            print(parsed.raw_statements)
            
        print("\n[Extracted Features]:")
        if updated_case.financial_features:
            print(updated_case.financial_features.model_dump_json(indent=2))
        else:
            print("No features extracted.")

    except Exception as e:
        print(f"\nGraph execution failed: {e}")
        print("Did you set your OPENROUTER_API_KEY in the .env file?")

if __name__ == "__main__":
    test_fis()
