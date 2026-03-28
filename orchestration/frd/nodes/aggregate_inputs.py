"""Organize SIS (and future FIS) inputs for FRD scoring."""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional

from shared.schemas.frd import FinancialProfile


def _unwrap_sis_bundle(sis_output: Dict[str, Any]) -> Dict[str, Any]:
    if sis_output.get("_sis_bundle_v1") and isinstance(sis_output.get("sis_output"), dict):
        return sis_output["sis_output"]
    return sis_output


def aggregate_inputs(
    sis_output: dict,
    financial_profile: Optional[dict] = None,
) -> dict:
    """
    Organize inputs for score_risk.

    Args:
        sis_output: SISOutput dict (company_id, signals, metadata), or a v1 bundle
            containing ``sis_output``.
        financial_profile: Raw FIS FinancialProfile dict; validated when provided.

    Returns:
        dict with:
        - company_id: str
        - signals: list of signal dicts
        - sector_signals: list of signals where event_type == "market_industry_risks"
        - financial_profile: validated FinancialProfile or None
        - documents_processed: int (from metadata)
    """
    core = _unwrap_sis_bundle(sis_output)
    company_id = str(core.get("company_id", ""))
    signals: List[Dict[str, Any]] = list(core.get("signals") or [])
    meta = core.get("metadata") or {}
    documents_processed = int(meta.get("documents_processed", 0))

    sector_signals = [s for s in signals if str(s.get("event_type", "")) == "market_industry_risks"]

    validated_fp: Optional[FinancialProfile] = None
    if financial_profile is not None:
        try:
            validated_fp = FinancialProfile.model_validate(financial_profile)
        except Exception as exc:  # pragma: no cover - defensive
            warnings.warn(
                f"FinancialProfile validation failed; proceeding without financial data: {exc}",
                UserWarning,
                stacklevel=2,
            )
            validated_fp = None

    return {
        "company_id": company_id,
        "signals": signals,
        "sector_signals": sector_signals,
        "financial_profile": validated_fp,
        "documents_processed": documents_processed,
    }
