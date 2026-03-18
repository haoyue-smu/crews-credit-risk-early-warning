"""LangExtract few-shot examples for SIS extraction.

These are the first concrete examples for Phase 2: they teach the model what
credit-relevant signals look like and how to ground them in exact text spans.
"""

from __future__ import annotations

import json
from pathlib import Path

from shared.taxonomy import EventCategory, Severity

try:
    import langextract as lx  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    lx = None  # type: ignore[assignment]


def _load_doc_001_text() -> str:
    """Load doc_001 full_text for few-shot examples."""

    project_root = Path(__file__).resolve().parents[3]
    doc_path = (
        project_root
        / "data"
        / "local"
        / "hyflux"
        / "doc_001_reuters_debt_restructuring.json"
    )
    payload = json.loads(doc_path.read_text(encoding="utf-8"))
    return str(payload["full_text"])


def get_sis_example_data() -> list["lx.data.ExampleData"]:
    """Return SIS few-shot `ExampleData` for LangExtract."""

    if lx is None:  # pragma: no cover
        raise ModuleNotFoundError(
            "langextract is required to build LangExtract few-shot examples."
        )

    text = _load_doc_001_text()

    debt_restructuring_text = (
        "Hyflux filed its application in May 2018 to the Singapore High Court under Section 211B for a court-supervised debt restructuring."
    )
    payment_default_text = (
        "The filing showed Hyflux had defaulted on the S$14.9 million perpetual securities interest payment due at the time."
    )
    market_value_decline_text = (
        "Hyflux's market value, which had once peaked near S$2.1 billion, had since fallen to about S$165 million."
    )

    # ExampleData A: teach all three signals in order of appearance.
    example_a = lx.data.ExampleData(
        text=text,
        extractions=[
            lx.data.Extraction(
                extraction_class=EventCategory.financial_distress_signals.value,
                extraction_text=debt_restructuring_text,
                attributes={
                    "event_type": EventCategory.financial_distress_signals.value,
                    "event_subtype": "debt_restructuring",
                    "severity": Severity.high.value,
                    "company_id": "hyflux",
                    "source_name": "Reuters",
                },
            ),
            lx.data.Extraction(
                extraction_class=EventCategory.financial_distress_signals.value,
                extraction_text=payment_default_text,
                attributes={
                    "event_type": EventCategory.financial_distress_signals.value,
                    "event_subtype": "payment_default",
                    "severity": Severity.high.value,
                    "company_id": "hyflux",
                    "source_name": "Reuters",
                },
            ),
            lx.data.Extraction(
                extraction_class=EventCategory.financial_distress_signals.value,
                extraction_text=market_value_decline_text,
                attributes={
                    "event_type": EventCategory.financial_distress_signals.value,
                    "event_subtype": "market_value_decline",
                    "severity": Severity.medium.value,
                    "company_id": "hyflux",
                    "source_name": "Reuters",
                },
            ),
        ],
    )

    # ExampleData B: a smaller subset (debt + payment) still in-text order.
    example_b = lx.data.ExampleData(
        text=text,
        extractions=[
            lx.data.Extraction(
                extraction_class=EventCategory.financial_distress_signals.value,
                extraction_text=debt_restructuring_text,
                attributes={
                    "event_type": EventCategory.financial_distress_signals.value,
                    "event_subtype": "debt_restructuring",
                    "severity": Severity.high.value,
                    "company_id": "hyflux",
                    "source_name": "Reuters",
                },
            ),
            lx.data.Extraction(
                extraction_class=EventCategory.financial_distress_signals.value,
                extraction_text=payment_default_text,
                attributes={
                    "event_type": EventCategory.financial_distress_signals.value,
                    "event_subtype": "payment_default",
                    "severity": Severity.high.value,
                    "company_id": "hyflux",
                    "source_name": "Reuters",
                },
            ),
        ],
    )

    # ExampleData C: payment + market value decline subset.
    example_c = lx.data.ExampleData(
        text=text,
        extractions=[
            lx.data.Extraction(
                extraction_class=EventCategory.financial_distress_signals.value,
                extraction_text=payment_default_text,
                attributes={
                    "event_type": EventCategory.financial_distress_signals.value,
                    "event_subtype": "payment_default",
                    "severity": Severity.high.value,
                    "company_id": "hyflux",
                    "source_name": "Reuters",
                },
            ),
            lx.data.Extraction(
                extraction_class=EventCategory.financial_distress_signals.value,
                extraction_text=market_value_decline_text,
                attributes={
                    "event_type": EventCategory.financial_distress_signals.value,
                    "event_subtype": "market_value_decline",
                    "severity": Severity.medium.value,
                    "company_id": "hyflux",
                    "source_name": "Reuters",
                },
            ),
        ],
    )

    return [example_a, example_b, example_c]

