"""LangExtract few-shot examples for SIS extraction.

These Phase 2 examples are used to teach the model which credit-relevant
signals to extract, including the event category and severity.
"""

from __future__ import annotations

import json
from pathlib import Path

from shared.taxonomy import EventCategory, Severity

try:
    import langextract as lx  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    lx = None  # type: ignore[assignment]


def _load_hyflux_doc_full_text(filename: str) -> str:
    """Load a Hyflux JSON doc's `full_text`."""

    project_root = Path(__file__).resolve().parents[3]
    doc_path = project_root / "data" / "local" / "hyflux" / filename
    payload = json.loads(doc_path.read_text(encoding="utf-8"))
    return str(payload["full_text"])


def get_sis_example_data() -> list["lx.data.ExampleData"]:
    """Return the Phase 2 SIS few-shot `ExampleData` list."""

    if lx is None:  # pragma: no cover
        raise ModuleNotFoundError(
            "langextract is required to build LangExtract few-shot examples."
        )

    # Example A (doc_001): financial distress signals.
    text_001 = _load_hyflux_doc_full_text("doc_001_reuters_debt_restructuring.json")
    debt_restructuring_text = (
        "Hyflux filed its application in May 2018 to the Singapore High Court under Section 211B for a court-supervised debt restructuring."
    )
    payment_default_text = (
        "The filing showed Hyflux had defaulted on the S$14.9 million perpetual securities interest payment due at the time."
    )

    example_a = lx.data.ExampleData(
        text=text_001,
        extractions=[
            lx.data.Extraction(
                extraction_class=EventCategory.financial_distress_signals.value,
                extraction_text=debt_restructuring_text,
                attributes={
                    "event_subtype": "debt_restructuring",
                    "severity": Severity.high.value,
                },
            ),
            lx.data.Extraction(
                extraction_class=EventCategory.financial_distress_signals.value,
                extraction_text=payment_default_text,
                attributes={
                    "event_subtype": "payment_default",
                    "severity": Severity.high.value,
                },
            ),
        ],
    )

    # Example B (doc_002): reputation/sentiment + management governance.
    text_002 = _load_hyflux_doc_full_text("doc_002_glassdoor_employee_reviews.json")
    employee_satisfaction_decline_text = (
        "Employee Review Excerpt 1 (Feb 2018): Morale at Hyflux has been low for months."
    )
    leadership_uncertainty_text = (
        "Employee Review Excerpt 2 (Mar 2018): There is a lot of management uncertainty."
    )

    example_b = lx.data.ExampleData(
        text=text_002,
        extractions=[
            lx.data.Extraction(
                extraction_class=EventCategory.reputation_sentiment.value,
                extraction_text=employee_satisfaction_decline_text,
                attributes={
                    "event_subtype": "employee_satisfaction_decline",
                    "severity": Severity.medium.value,
                },
            ),
            lx.data.Extraction(
                extraction_class=EventCategory.management_governance.value,
                extraction_text=leadership_uncertainty_text,
                attributes={
                    "event_subtype": "leadership_uncertainty",
                    "severity": Severity.medium.value,
                },
            ),
        ],
    )

    # Example C (doc_004): company IR statement — denials / reaffirmations as positive_signals.
    text_004 = _load_hyflux_doc_full_text("doc_004_company_statement_denial.json")
    denial_restructuring_text = (
        "The company states categorically that Hyflux has not filed any formal application for "
        "court-supervised debt restructuring with the Singapore High Court, and that any suggestion "
        "that such a filing has been made is inaccurate."
    )
    operations_normal_text = (
        "Management reports that operations across Hyflux's desalination, water treatment, and related "
        "energy activities are running normally, with facilities meeting service commitments and "
        "commercial schedules."
    )

    example_c = lx.data.ExampleData(
        text=text_004,
        extractions=[
            lx.data.Extraction(
                extraction_class=EventCategory.positive_signals.value,
                extraction_text=denial_restructuring_text,
                attributes={
                    "event_subtype": "denial_of_debt_restructuring",
                    "severity": Severity.positive.value,
                },
            ),
            lx.data.Extraction(
                extraction_class=EventCategory.positive_signals.value,
                extraction_text=operations_normal_text,
                attributes={
                    "event_subtype": "operations_reaffirmation",
                    "severity": Severity.positive.value,
                },
            ),
        ],
    )

    # Keep extractions in the order they appear in each example document.
    return [example_a, example_b, example_c]

