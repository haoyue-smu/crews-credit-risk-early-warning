"""Integration test for the Financial Ingestion Subgraph (FIS).

Runs the full FIS pipeline against a dummy XML financial document:
  1. Assembles a CaseState with company profile + uploaded document
  2. Compiles and invokes the FIS LangGraph
  3. Prints parsed statements, financial features, ratios, and Z-Score

Requires: OPENROUTER_API_KEY set in .env (makes live LLM calls).
Marked ``integration`` and skipped when the key is not set.
"""

import json
import os
import sys
from datetime import datetime

import pytest
from dotenv import load_dotenv

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from shared.states.case_state import (
    CaseState,
    CompanyProfile,
    UploadedFinancialDocument,
)
from orchestration.fis.graph import build_fis_graph

load_dotenv()


def create_test_xml() -> str:
    """Returns path to samples/dummy_financials.xml."""
    filepath = os.path.join(
        os.path.dirname(__file__), "..", "..", "samples", "dummy_financials.xml"
    )
    filepath = os.path.abspath(filepath)
    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"dummy_financials.xml not found at {filepath}. "
            "Run from the project root directory."
        )
    return filepath


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="integration test: OPENROUTER_API_KEY not set",
)
def test_fis():
    print("=" * 60)
    print("FIS Integration Test")
    print("=" * 60)

    # --- 1. Assemble mock case ---
    print("\n1. Assembling Mock Case State...")
    dummy_file = create_test_xml()
    print(f"   Using: {dummy_file}")

    case = CaseState(
        case_id="test-fis-001",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        company=CompanyProfile(
            company_id="comp-acme",
            company_name="Acme Manufacturing Corp",
            company_type="private",
            jurisdiction="US",
            industry_sector="manufacturing",
            is_manufacturing=True,
        ),
        uploaded_financial_documents=[
            UploadedFinancialDocument(
                document_id="doc-1",
                filename="dummy_financials.xml",
                file_type="xml",
                local_path=dummy_file,
                uploaded_at=datetime.utcnow(),
                document_role="annual_report",
            )
        ],
    )

    # --- 2. Compile graph ---
    print("\n2. Compiling FIS Graph...")
    graph = build_fis_graph()
    print("   Graph compiled successfully.")

    # --- 3. Invoke ---
    print("\n3. Invoking Graph (calling OpenRouter Gemini Flash)...")
    try:
        final_state = graph.invoke({"case": case})
        updated_case: CaseState = final_state["case"]

        # --- Results ---
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)

        print(f"\nFinal Status: {updated_case.status}")
        print(f"Warnings: {updated_case.warnings}")

        # Parsed documents
        print(f"\n--- Parsed Documents ({len(updated_case.parsed_financial_documents)}) ---")
        for pd in updated_case.parsed_financial_documents:
            print(f"  Doc [{pd.document_id}] Parser: {pd.parser_name}")
            print(f"  Fiscal Year: {pd.fiscal_year}, Period: {pd.fiscal_period}, Currency: {pd.currency}")
            if pd.warnings:
                print(f"  Warnings: {pd.warnings}")

        # Financial features
        ff = updated_case.financial_features
        if ff:
            print("\n--- Financial Features ---")
            print(f"  Period: FY{ff.period.fiscal_year} ({ff.period.currency})")

            print("\n  [Income Statement]")
            for k, v in ff.income_statement.model_dump().items():
                if v is not None:
                    print(f"    {k}: {v:,.2f}" if isinstance(v, float) else f"    {k}: {v}")

            print("\n  [Balance Sheet]")
            for k, v in ff.balance_sheet.model_dump().items():
                if v is not None:
                    print(f"    {k}: {v:,.2f}" if isinstance(v, float) else f"    {k}: {v}")

            print("\n  [Cash Flow]")
            for k, v in ff.cash_flow.model_dump().items():
                if v is not None:
                    print(f"    {k}: {v:,.2f}" if isinstance(v, float) else f"    {k}: {v}")

            print("\n  [Financial Ratios]")
            for k, v in ff.ratios.model_dump(exclude={"computation_notes"}).items():
                if v is not None:
                    print(f"    {k}: {v:.4f}")
            if ff.ratios.computation_notes:
                print(f"    Notes: {ff.ratios.computation_notes}")

            print("\n  [Altman Z-Score]")
            if ff.current_z_score:
                z = ff.current_z_score
                print(f"    Score: {z.score}")
                print(f"    Zone: {z.zone.value.upper()}")
                print(f"    Formula: {z.formula_used.value}")
                print(f"    Thresholds: safe >= {z.zone_thresholds.get('safe')}, distress < {z.zone_thresholds.get('distress')}")
                if z.components:
                    print("    Components:")
                    for ck, cv in z.components.items():
                        print(f"      {ck}: {cv}")
                if z.notes:
                    print(f"    Notes: {z.notes}")
            else:
                print("    No Z-Score computed.")

            if ff.historical_z_scores:
                print(f"\n  [Historical Z-Scores ({len(ff.historical_z_scores)} periods)]")
                for hz in ff.historical_z_scores:
                    print(f"    {hz.period_label}: {hz.score} ({hz.zone.value})")

            if ff.peer_comparison:
                pc = ff.peer_comparison
                print(f"\n  [Peer Comparison — {pc.industry_sector}]")
                print(f"    Industry Median Z: {pc.industry_median_z}")
                print(f"    Safe Zone %: {pc.industry_safe_zone_pct}")
                print(f"    Grey Zone %: {pc.industry_grey_zone_pct}")
                print(f"    Distress Zone %: {pc.industry_distress_zone_pct}")
                if pc.notes:
                    print(f"    Notes: {pc.notes}")

            if ff.warnings:
                print(f"\n  Feature Warnings: {ff.warnings}")
        else:
            print("\nNo financial features extracted.")

        # Audit log
        print(f"\n--- Audit Log ({len(updated_case.audit_log)} events) ---")
        for ae in updated_case.audit_log:
            print(f"  [{ae.timestamp.strftime('%H:%M:%S')}] {ae.node_name}: {ae.event}")
            if ae.details:
                for dk, dv in ae.details.items():
                    if dk != "traceback":
                        print(f"    {dk}: {dv}")

    except Exception as e:
        print(f"\nGraph execution failed: {e}")
        print("\nDid you set OPENROUTER_API_KEY in the .env file?")
        raise

    # FIS reports fis_features_extracted even when parsing failed, so check the outputs.
    assert updated_case.status == "fis_features_extracted", updated_case.status
    assert any(
        p.raw_statements and "fis_openrouter_error" not in p.parser_name
        for p in updated_case.parsed_financial_documents
    ), "no document parsed successfully"
    ff = updated_case.financial_features
    assert ff is not None and ff.current_z_score is not None, "no Z-Score computed"
    assert ff.current_z_score.score is not None, ff.current_z_score


if __name__ == "__main__":
    test_fis()
