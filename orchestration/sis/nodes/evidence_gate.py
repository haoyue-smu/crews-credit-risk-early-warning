"""SIS evidence gate placeholder (Phase 3/4).

Applies the single human interrupt point at evidence_gate:
- If evidence is sufficient -> `resolution_path="auto"`
- If evidence is weak for high severity -> `resolution_path="pending"`
- If evidence is ambiguous (including disputed conflicts) -> `resolution_path="auto"` + `ambiguous=True`
"""

from __future__ import annotations

from shared.schemas.signals import SISOutput, Signal


def evidence_gate(company_id: str, signals: list[Signal]) -> SISOutput:
    """Gate signals based on evidence sufficiency and set SIS/HITL fields.

    Args:
        company_id: Company identifier for the output contract to FRD.
        signals: Signals produced by conflict resolution.

    Returns:
        SISOutput containing signals and metadata for FRD report generation.
    """

    raise NotImplementedError("Phase 2/3/4")

