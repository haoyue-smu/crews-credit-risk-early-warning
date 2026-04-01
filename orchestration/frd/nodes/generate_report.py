"""FRD Phase 3 — LLM-generated analyst narrative (does not alter traffic light)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from orchestration.frd.prompts.report_template import REPORT_SYSTEM_PROMPT, build_report_prompt

_SECTION_KEYS = [
    "executive_summary",
    "key_risk_findings",
    "financial_health_assessment",
    "signal_details",
    "disputed_and_ambiguous",
    "data_quality_notes",
    "recommended_actions",
]

_SECTION_TITLES = {
    "executive_summary": "Executive Summary",
    "key_risk_findings": "Key Risk Findings",
    "financial_health_assessment": "Financial Health Assessment",
    "signal_details": "Signal Details",
    "disputed_and_ambiguous": "Disputed & Ambiguous Signals",
    "data_quality_notes": "Data Quality Notes",
    "recommended_actions": "Recommended Actions",
}


def _response_text(response: Any) -> str:
    t = getattr(response, "text", None)
    if t:
        return str(t)
    cands = getattr(response, "candidates", None) or []
    for cand in cands:
        content = getattr(cand, "content", None)
        parts = getattr(content, "parts", None) if content is not None else None
        if not parts:
            continue
        chunks: List[str] = []
        for p in parts:
            txt = getattr(p, "text", None)
            if txt:
                chunks.append(str(txt))
        if chunks:
            return "".join(chunks)
    return ""


def _strip_markdown_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _extract_json_object(text: str) -> Optional[dict]:
    raw = _strip_markdown_fences(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def _normalize_sections(data: Optional[dict]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(data, dict):
        data = {}
    for key in _SECTION_KEYS:
        val = data.get(key)
        out[key] = str(val).strip() if val is not None else "N/A"
    return out


def _build_full_narrative(sections: Dict[str, str]) -> str:
    parts: List[str] = []
    for key in _SECTION_KEYS:
        title = _SECTION_TITLES[key]
        content = sections.get(key, "N/A")
        parts.append(f"## {title}\n\n{content}\n")
    return "\n".join(parts)


def _fallback_result(raw: str, model_id: str, ts: str) -> dict:
    return {
        "sections": {"error": "Failed to generate report"},
        "full_narrative": f"## Error\n\nFailed to generate report.\n\n{raw[:4000]}",
        "model_used": model_id,
        "generation_timestamp": ts,
    }


def generate_report(
    risk_score: dict,
    signals: List[dict],
    financial_profile: dict | None,
    documents_processed: int,
    *,
    model_id: str = "gemini-2.5-flash",
) -> dict:
    """
    Generate an analyst-facing credit risk report using LLM.

    Returns:
        dict with sections (structured), full_narrative (markdown), model_used, generation_timestamp.
    """
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    user_block = build_report_prompt(
        risk_score=risk_score,
        signals=signals,
        financial_profile=financial_profile,
        documents_processed=documents_processed,
    )
    full_prompt = f"{REPORT_SYSTEM_PROMPT.strip()}\n\n{user_block}"

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return _fallback_result("Missing GEMINI_API_KEY in environment/.env.", model_id, ts)

    try:
        from google import genai  # type: ignore
    except ModuleNotFoundError as exc:
        return _fallback_result(f"google-genai not installed: {exc}", model_id, ts)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_id,
            contents=full_prompt,
            config={"temperature": 0.3},
        )
        raw_text = _response_text(response)
    except Exception as exc:  # pragma: no cover - network/API
        return _fallback_result(f"LLM call failed: {exc!r}", model_id, ts)

    parsed = _extract_json_object(raw_text)
    if parsed is None:
        return _fallback_result(raw_text or "(empty response)", model_id, ts)

    sections = _normalize_sections(parsed)
    return {
        "sections": sections,
        "full_narrative": _build_full_narrative(sections),
        "model_used": model_id,
        "generation_timestamp": ts,
    }
