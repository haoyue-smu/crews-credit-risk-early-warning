"""Unit tests for shared SIS Pydantic schemas.

These tests cover both valid constructions and common invalid cases.
"""

from __future__ import annotations

import unittest
from datetime import datetime

from pydantic import ValidationError

from shared.schemas.documents import DocumentInput, SourceType
from shared.schemas.retrieval import TargetedRetrievalRequest
from shared.schemas.signals import (
    CharInterval,
    Evidence,
    ConflictStatus,
    ResolutionPath,
    ReviewStatus,
    SISOutput,
    Signal,
    SISMetadata,
)
from shared.taxonomy import EventCategory, Severity


class TestSISSharedSchemas(unittest.TestCase):
    def test_document_input_valid(self) -> None:
        doc = DocumentInput(
            document_id="doc_001",
            company_id="hyflux",
            source_name="Reuters",
            source_type=SourceType.news,
            published_date=datetime(2026, 3, 15, 10, 0, 0),
            fetched_date=datetime(2026, 3, 16, 12, 0, 0),
            url="https://example.com/article",
            full_text="Company issues credit concerns amid audit findings.",
            language="en",
            source_quality_score=0.92,
        )
        self.assertEqual(doc.company_id, "hyflux")

    def test_document_input_invalid_quality_score(self) -> None:
        with self.assertRaises(ValidationError):
            DocumentInput(
                document_id="doc_001",
                company_id="hyflux",
                source_name="Reuters",
                source_type=SourceType.news,
                published_date=datetime(2026, 3, 15, 10, 0, 0),
                fetched_date=datetime(2026, 3, 16, 12, 0, 0),
                url="https://example.com/article",
                full_text="Company issues credit concerns amid audit findings.",
                language="en",
                source_quality_score=1.5,
            )

    def test_evidence_valid(self) -> None:
        ci = CharInterval(start=100, end=120)
        evidence = Evidence(
            source_name="Reuters",
            document_id="doc_001",
            date=datetime(2026, 3, 15, 10, 0, 0),
            snippet="CFO resigned amid audit delays.",
            char_interval=ci,
            source_quality=0.9,
        )
        self.assertEqual(evidence.char_interval.start, 100)

    def test_evidence_invalid_interval_order(self) -> None:
        with self.assertRaises(ValidationError):
            Evidence(
                source_name="Reuters",
                document_id="doc_001",
                date=datetime(2026, 3, 15, 10, 0, 0),
                snippet="CFO resigned amid audit delays.",
                char_interval=CharInterval(start=10, end=5),
                source_quality=0.9,
            )

    def test_signal_valid(self) -> None:
        ci = CharInterval(start=100, end=120)
        evidence = Evidence(
            source_name="Reuters",
            document_id="doc_001",
            date=datetime(2026, 3, 15, 10, 0, 0),
            snippet="CFO resigned amid audit delays.",
            char_interval=ci,
            source_quality=0.9,
        )
        signal = Signal(
            signal_id="sig_001",
            event_type=EventCategory.management_governance,
            event_subtype="ceo_departure",
            severity=Severity.high,
            confidence=0.85,
            ambiguous=False,
            conflict_status=ConflictStatus.no_conflict,
            resolution_path=ResolutionPath.auto,
            review_status=None,
            evidence=[evidence],
        )
        self.assertEqual(signal.signal_id, "sig_001")

    def test_signal_invalid_review_status_rules(self) -> None:
        ci = CharInterval(start=100, end=120)
        evidence = Evidence(
            source_name="Reuters",
            document_id="doc_001",
            date=datetime(2026, 3, 15, 10, 0, 0),
            snippet="CFO resigned amid audit delays.",
            char_interval=ci,
            source_quality=0.9,
        )

        with self.assertRaises(ValidationError):
            Signal(
                signal_id="sig_001",
                event_type=EventCategory.management_governance,
                event_subtype="ceo_departure",
                severity=Severity.high,
                confidence=0.85,
                ambiguous=False,
                conflict_status=ConflictStatus.no_conflict,
                resolution_path=ResolutionPath.auto,
                review_status=ReviewStatus.verified,
                evidence=[evidence],
            )

    def test_sis_output_valid(self) -> None:
        ci = CharInterval(start=100, end=120)
        evidence = Evidence(
            source_name="Reuters",
            document_id="doc_001",
            date=datetime(2026, 3, 15, 10, 0, 0),
            snippet="CFO resigned amid audit delays.",
            char_interval=ci,
            source_quality=0.9,
        )
        signal = Signal(
            signal_id="sig_001",
            event_type=EventCategory.management_governance,
            event_subtype="ceo_departure",
            severity=Severity.high,
            confidence=0.85,
            ambiguous=False,
            conflict_status=ConflictStatus.no_conflict,
            resolution_path=ResolutionPath.auto,
            review_status=None,
            evidence=[evidence],
        )
        metadata = SISMetadata(
            documents_processed=1,
            signals_extracted=1,
            signals_auto_verified=1,
            signals_ambiguous=0,
            signals_pending_review=0,
            signals_rejected=0,
            timestamp=datetime(2026, 3, 18, 10, 0, 0),
        )
        output = SISOutput(company_id="hyflux", signals=[signal], metadata=metadata)
        self.assertEqual(output.metadata.documents_processed, 1)

    def test_sis_output_invalid_missing_timestamp(self) -> None:
        ci = CharInterval(start=100, end=120)
        evidence = Evidence(
            source_name="Reuters",
            document_id="doc_001",
            date=datetime(2026, 3, 15, 10, 0, 0),
            snippet="CFO resigned amid audit delays.",
            char_interval=ci,
            source_quality=0.9,
        )
        signal = Signal(
            signal_id="sig_001",
            event_type=EventCategory.management_governance,
            event_subtype="ceo_departure",
            severity=Severity.high,
            confidence=0.85,
            ambiguous=False,
            conflict_status=ConflictStatus.no_conflict,
            resolution_path=ResolutionPath.auto,
            review_status=None,
            evidence=[evidence],
        )

        with self.assertRaises(ValidationError):
            SISOutput(
                company_id="hyflux",
                signals=[signal],
                metadata={
                    "documents_processed": 1,
                    "signals_extracted": 1,
                    "signals_auto_verified": 1,
                    "signals_ambiguous": 0,
                    "signals_pending_review": 0,
                    "signals_rejected": 0,
                    # timestamp is intentionally missing
                },
            )

    def test_targeted_retrieval_request_valid(self) -> None:
        req = TargetedRetrievalRequest(
            company_id="hyflux",
            keywords=["audit delays", "liquidity stress"],
            target_source_types=["news", "filing"],
            signal_context="Need more evidence about potential credit deterioration.",
        )
        self.assertEqual(req.company_id, "hyflux")

    def test_targeted_retrieval_request_invalid_empty_keywords(self) -> None:
        with self.assertRaises(ValidationError):
            TargetedRetrievalRequest(
                company_id="hyflux",
                keywords=[],
                target_source_types=["news", "filing"],
                signal_context="Need more evidence about potential credit deterioration.",
            )


if __name__ == "__main__":
    unittest.main()

