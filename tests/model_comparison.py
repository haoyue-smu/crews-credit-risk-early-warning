"""
Model Comparison Script — Extract & Conflict nodes
====================================================

Runs SIS extract (3 workhorse models) and conflict (workhorse vs premium)
on Hyflux test data. Captures token usage, cost, latency, and signal quality.

Usage:
    python -m tests.model_comparison

Output:
    data/local/hyflux/model_comparison_results.json
    + printed comparison tables

Requires: OPENROUTER_API_KEY in .env
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import OpenAI
from shared.config import settings
from shared.schemas.documents import DocumentInput
from shared.schemas.signals import CharInterval, Evidence, Signal
from shared.taxonomy import EventCategory, Severity
from orchestration.sis.prompts.templates import EXTRACTION_PROMPT

# ---------------------------------------------------------------------------
# Pricing table (per token, not per million)
# ---------------------------------------------------------------------------
PRICING = {
    "google/gemini-2.5-flash":   {"input": 0.30e-6, "output": 2.50e-6},
    "openai/gpt-4o-mini":        {"input": 0.15e-6, "output": 0.60e-6},
    "anthropic/claude-3.5-haiku": {"input": 0.80e-6, "output": 4.00e-6},
    "google/gemini-2.5-pro":     {"input": 1.25e-6, "output": 10.00e-6},
}

EXTRACT_MODELS = [
    "google/gemini-2.5-flash",
    "openai/gpt-4o-mini",
    "anthropic/claude-3.5-haiku",
]

CONFLICT_MODELS = [
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
]

_BASE_URL = "https://openrouter.ai/api/v1"

_FORMAT_INSTRUCTIONS = (
    "\n\nReturn a JSON object with a single key \"extractions\" containing an array. "
    "Each element must have exactly these keys:\n"
    "- \"event_type\": one of the allowed EventCategory values\n"
    "- \"event_subtype\": a concise snake_case label\n"
    "- \"severity\": exactly one of: low, medium, high, positive\n"
    "- \"extraction_text\": the exact verbatim span copied from the input text\n\n"
    "If no relevant signals are found, return {\"extractions\": []}."
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_hyflux_docs() -> list[DocumentInput]:
    root = Path(__file__).resolve().parents[1]
    hyflux_dir = root / "data" / "local" / "hyflux"
    docs = []
    for fpath in sorted(hyflux_dir.glob("doc_*.json")):
        payload = json.loads(fpath.read_text(encoding="utf-8"))
        docs.append(DocumentInput.model_validate(payload))
    return docs


def load_verification_items() -> tuple[list[dict[str, Any]], list[DocumentInput]]:
    """Load verification items using run_conflict.py's proven parsing logic."""
    root = Path(__file__).resolve().parents[1]
    hyflux_root = root / "data" / "local" / "hyflux"

    # Reuse run_conflict.py's loaders (they handle the old LangExtract format)
    sys.path.insert(0, str(root))
    from orchestration.sis.run_conflict import (
        load_hyflux_documents,
        signals_from_extraction_results,
        load_verification_index,
        build_verification_items,
    )

    docs_by_id = load_hyflux_documents(hyflux_root)
    docs_list = list(docs_by_id.values())

    extraction_path = hyflux_root / "extraction_results.jsonl"
    verification_path = hyflux_root / "verification_results.jsonl"

    signals = signals_from_extraction_results(extraction_path, docs_list)
    if not signals:
        return [], docs_list

    verification_index = load_verification_index(verification_path)
    items = build_verification_items(signals, verification_index)
    return items, docs_list


# ---------------------------------------------------------------------------
# Extract comparison
# ---------------------------------------------------------------------------

def run_extract_one_doc(client: OpenAI, model: str, doc: DocumentInput) -> dict:
    """Run extraction on one document, return signals + usage."""
    system_prompt = EXTRACTION_PROMPT + _FORMAT_INSTRUCTIONS
    user_prompt = f"Extract credit-relevant signals from this text:\n\n{doc.full_text}"

    t0 = time.time()
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    latency = time.time() - t0

    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0

    data = json.loads(response.choices[0].message.content)
    extractions = data.get("extractions", [])

    # Parse into signals
    signals = []
    for idx, ex in enumerate(extractions):
        if not isinstance(ex, dict):
            continue
        try:
            event_type = EventCategory(str(ex.get("event_type", "")))
            severity = Severity(str(ex.get("severity", "")))
        except Exception:
            continue
        signals.append({
            "event_type": event_type.value,
            "event_subtype": str(ex.get("event_subtype", "")),
            "severity": severity.value,
            "extraction_text": str(ex.get("extraction_text", ""))[:100],
        })

    return {
        "document_id": doc.document_id,
        "signal_count": len(signals),
        "signals": signals,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_seconds": round(latency, 2),
    }


def run_extract_comparison(docs: list[DocumentInput]) -> list[dict]:
    """Run extraction across all models, all docs."""
    settings.require_llm()
    results = []

    for model in EXTRACT_MODELS:
        print(f"\n{'='*60}")
        print(f"EXTRACT — {model}")
        print(f"{'='*60}")

        client = OpenAI(base_url=_BASE_URL, api_key=settings.openrouter_api_key)
        total_prompt = 0
        total_completion = 0
        total_signals = 0
        total_latency = 0
        all_signals = []
        doc_results = []

        for doc in docs:
            print(f"  Processing {doc.document_id}...", end=" ", flush=True)
            try:
                res = run_extract_one_doc(client, model, doc)
                doc_results.append(res)
                total_prompt += res["prompt_tokens"]
                total_completion += res["completion_tokens"]
                total_signals += res["signal_count"]
                total_latency += res["latency_seconds"]
                all_signals.extend(res["signals"])
                print(f"{res['signal_count']} signals, {res['latency_seconds']}s")
            except Exception as e:
                print(f"FAILED: {e}")
                doc_results.append({"document_id": doc.document_id, "error": str(e)})

        # Cost calculation
        pricing = PRICING.get(model, {"input": 0, "output": 0})
        cost = total_prompt * pricing["input"] + total_completion * pricing["output"]

        # Signal analysis
        event_types = Counter(s["event_type"] for s in all_signals)
        severities = Counter(s["severity"] for s in all_signals)

        # Check key signals (Hyflux ground truth)
        subtypes = {s["event_subtype"] for s in all_signals}
        key_signals_found = {
            "debt_restructuring": any("restructur" in st for st in subtypes),
            "employee_dissatisfaction": any("employee" in st or "morale" in st for st in subtypes),
            "asset_sale_difficulty": any("asset" in st or "tuaspring" in st for st in subtypes),
            "company_denial": any("denial" in st or "reaffirm" in st for st in subtypes),
        }

        result = {
            "model": model,
            "test": "extract",
            "total_signals": total_signals,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "cost_usd": round(cost, 6),
            "total_latency_seconds": round(total_latency, 2),
            "avg_latency_per_doc": round(total_latency / len(docs), 2),
            "event_type_distribution": dict(event_types),
            "severity_distribution": dict(severities),
            "key_signals_found": key_signals_found,
            "doc_results": doc_results,
        }
        results.append(result)

        print(f"\n  Total: {total_signals} signals, {total_prompt+total_completion} tokens, "
              f"${cost:.4f}, {total_latency:.1f}s")

    return results


# ---------------------------------------------------------------------------
# Conflict comparison
# ---------------------------------------------------------------------------

def run_conflict_comparison(docs: list[DocumentInput]) -> list[dict]:
    """Run conflict resolution across workhorse vs premium."""
    items, docs_list = load_verification_items()
    if not items:
        print("\nNo extraction/verification data found — skipping conflict comparison.")
        print("Run 'python -m orchestration.sis.run_extraction' first.")
        return []
    docs = docs_list  # override the passed-in docs with the ones from hyflux

    results = []
    for model in CONFLICT_MODELS:
        print(f"\n{'='*60}")
        print(f"CONFLICT — {model}")
        print(f"{'='*60}")

        # Override model for this run
        os.environ["OPENROUTER_MODEL_SIS"] = model

        # Force reload shared.llm
        import importlib
        import shared.llm
        importlib.reload(shared.llm)

        from orchestration.sis.nodes.conflict import conflict_resolution

        t0 = time.time()
        working, summary = conflict_resolution(items, docs, max_workers=10)
        latency = time.time() - t0

        # We can't get exact tokens from conflict_resolution without modifying it,
        # so estimate from OpenRouter dashboard or use summary stats
        result = {
            "model": model,
            "test": "conflict",
            "input_signals": summary.get("total_input", 0),
            "output_signals": summary.get("total_output", 0),
            "nli_pairs_screened": summary.get("nli_pairs_screened", 0),
            "nli_contradictions_detected": summary.get("nli_contradictions_detected", 0),
            "llm_confirmed_contradictions": summary.get("llm_confirmed", 0),
            "duplicates_merged": summary.get("duplicates_merged", 0),
            "disputed": summary.get("disputed", 0),
            "positive_auto_ambiguous": summary.get("positive_auto_ambiguous", 0),
            "contradiction_explanations": summary.get("contradiction_explanations", []),
            "total_latency_seconds": round(latency, 2),
        }
        results.append(result)

        print(f"\n  NLI screened: {result['nli_pairs_screened']}")
        print(f"  NLI contradictions: {result['nli_contradictions_detected']}")
        print(f"  LLM confirmed: {result['llm_confirmed_contradictions']}")
        print(f"  Duplicates merged: {result['duplicates_merged']}")
        print(f"  Latency: {latency:.1f}s")

    return results


# ---------------------------------------------------------------------------
# Pretty print comparison tables
# ---------------------------------------------------------------------------

def print_extract_table(results: list[dict]) -> None:
    print("\n" + "=" * 80)
    print("EXTRACTION MODEL COMPARISON")
    print("=" * 80)

    # Header
    models = [r["model"].split("/")[-1] for r in results]
    header = f"{'Metric':<30}" + "".join(f"{m:>18}" for m in models)
    print(header)
    print("-" * len(header))

    rows = [
        ("Total Signals", [str(r["total_signals"]) for r in results]),
        ("Prompt Tokens", [f"{r['total_prompt_tokens']:,}" for r in results]),
        ("Completion Tokens", [f"{r['total_completion_tokens']:,}" for r in results]),
        ("Total Tokens", [f"{r['total_tokens']:,}" for r in results]),
        ("Cost (USD)", [f"${r['cost_usd']:.4f}" for r in results]),
        ("Total Latency (s)", [str(r["total_latency_seconds"]) for r in results]),
        ("Avg Latency/Doc (s)", [str(r["avg_latency_per_doc"]) for r in results]),
    ]

    for label, vals in rows:
        print(f"{label:<30}" + "".join(f"{v:>18}" for v in vals))

    # Event type breakdown
    print(f"\n{'Event Types':<30}" + "".join(f"{m:>18}" for m in models))
    print("-" * len(header))
    all_types = set()
    for r in results:
        all_types.update(r["event_type_distribution"].keys())
    for etype in sorted(all_types):
        vals = [str(r["event_type_distribution"].get(etype, 0)) for r in results]
        print(f"  {etype:<28}" + "".join(f"{v:>18}" for v in vals))

    # Severity breakdown
    print(f"\n{'Severity':<30}" + "".join(f"{m:>18}" for m in models))
    print("-" * len(header))
    for sev in ["high", "medium", "low", "positive"]:
        vals = [str(r["severity_distribution"].get(sev, 0)) for r in results]
        print(f"  {sev:<28}" + "".join(f"{v:>18}" for v in vals))

    # Key signals check
    print(f"\n{'Key Signals (Hyflux)':<30}" + "".join(f"{m:>18}" for m in models))
    print("-" * len(header))
    key_names = ["debt_restructuring", "employee_dissatisfaction", "asset_sale_difficulty", "company_denial"]
    for key in key_names:
        vals = ["✓" if r["key_signals_found"].get(key) else "✗" for r in results]
        print(f"  {key:<28}" + "".join(f"{v:>18}" for v in vals))


def print_conflict_table(results: list[dict]) -> None:
    if not results:
        return
    print("\n" + "=" * 80)
    print("CONFLICT RESOLUTION MODEL COMPARISON (workhorse vs premium)")
    print("=" * 80)

    models = [r["model"].split("/")[-1] for r in results]
    header = f"{'Metric':<35}" + "".join(f"{m:>22}" for m in models)
    print(header)
    print("-" * len(header))

    rows = [
        ("Input Signals", [str(r["input_signals"]) for r in results]),
        ("Output Signals", [str(r["output_signals"]) for r in results]),
        ("NLI Pairs Screened", [str(r["nli_pairs_screened"]) for r in results]),
        ("NLI Contradictions Detected", [str(r["nli_contradictions_detected"]) for r in results]),
        ("LLM Confirmed Contradictions", [str(r["llm_confirmed_contradictions"]) for r in results]),
        ("Duplicates Merged", [str(r["duplicates_merged"]) for r in results]),
        ("Disputed Signals", [str(r["disputed"]) for r in results]),
        ("Positive Auto-Ambiguous", [str(r["positive_auto_ambiguous"]) for r in results]),
        ("Latency (s)", [str(r["total_latency_seconds"]) for r in results]),
    ]

    for label, vals in rows:
        print(f"{label:<35}" + "".join(f"{v:>22}" for v in vals))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("MODEL COMPARISON — SIS Extract & Conflict Nodes")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)

    docs = load_hyflux_docs()
    print(f"\nLoaded {len(docs)} Hyflux documents")
    for d in docs:
        print(f"  {d.document_id}: {d.source_name} ({len(d.full_text)} chars)")

    # Part 1: Extract comparison
    extract_results = run_extract_comparison(docs)
    print_extract_table(extract_results)

    # Part 2: Conflict comparison
    conflict_results = run_conflict_comparison(docs)
    print_conflict_table(conflict_results)

    # Save all results
    output = {
        "timestamp": datetime.now().isoformat(),
        "hyflux_docs": len(docs),
        "extract_comparison": extract_results,
        "conflict_comparison": conflict_results,
        "pricing_table": {k: {"input_per_1M": v["input"] * 1e6, "output_per_1M": v["output"] * 1e6}
                          for k, v in PRICING.items()},
        "selection_rationale": {
            "filter_1_compliance": "MAS regulatory requirements limit LLM providers to those with "
                                   "financial-industry compliance certifications (SOC 2, ISO 27001) "
                                   "and clear data residency guarantees. This narrows the field to "
                                   "Google, OpenAI, and Anthropic.",
            "filter_2_task_profile": "Extract node = high-volume structured extraction → workhorse tier. "
                                     "Conflict node = semantic reasoning → workhorse vs premium comparison.",
            "models_tested": {
                "extract": ["google/gemini-2.5-flash", "openai/gpt-4o-mini", "anthropic/claude-3.5-haiku"],
                "conflict": ["google/gemini-2.5-flash (workhorse)", "google/gemini-2.5-pro (premium)"],
            },
        },
    }

    root = Path(__file__).resolve().parents[1]
    out_path = root / "data" / "local" / "hyflux" / "model_comparison_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\n\nResults saved to {out_path}")
    print("Done.")


if __name__ == "__main__":
    main()