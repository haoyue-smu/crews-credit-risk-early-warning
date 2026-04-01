"""Development script to run SIS extraction on local Hyflux data.

Run with:
    python -m orchestration.sis.run_extraction

Calls ``parallel_extract_signals`` (OpenRouter via OpenAI SDK) and prints results.
Pass ``--use-cache`` to skip API calls and replay cached ``extraction_results.jsonl``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from shared.schemas.documents import DocumentInput
from orchestration.sis.nodes.extract import parallel_extract_signals


def _iter_hyflux_documents(hyflux_dir: Path) -> Iterable[tuple[Path, DocumentInput]]:
    """Load and validate all *.json docs under a directory."""
    for path in sorted(hyflux_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        doc = DocumentInput.model_validate(payload)
        yield path, doc


def _run_cache_mode(hyflux_dir: Path, output_path: Path) -> None:
    """Print cached JSONL; do not call the API or save."""
    if not output_path.exists():
        print(f"No cache file at {output_path}; run without --use-cache first.")
        return

    text_to_label: dict[str, str] = {}
    for path, doc in _iter_hyflux_documents(hyflux_dir):
        text_to_label[doc.full_text] = path.name

    t0 = time.perf_counter()
    with output_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload: dict[str, Any] = json.loads(line)
            doc_id = str(payload.get("document_id", "unknown"))
            print(f"\n=== {doc_id} ===")
            print(json.dumps(payload, indent=2))

    elapsed = time.perf_counter() - t0
    print(f"\nTotal wall-clock time (cache replay): {elapsed:.1f}s")


def main() -> None:
    """Execute local extraction for Hyflux documents."""
    project_root = Path(__file__).resolve().parents[2]
    hyflux_dir = project_root / "data" / "local" / "hyflux"
    output_path = hyflux_dir / "extraction_results.jsonl"

    args = sys.argv[1:]
    use_cache = "--use-cache" in args
    force_recompute = "--no-cache" in args

    if use_cache and not force_recompute:
        print(f"Using cached extraction results from {output_path} (skip API).")
        _run_cache_mode(hyflux_dir, output_path)
        return

    doc_items: list[tuple[Path, DocumentInput]] = list(_iter_hyflux_documents(hyflux_dir))

    if not doc_items:
        print(f"No *.json documents found under {hyflux_dir}")
        return

    for path, doc in doc_items:
        print(f"Found: {path.name} (company_id={doc.company_id}, source_type={doc.source_type})")

    docs = [doc for _, doc in doc_items]
    print(f"\nExtracting {len(docs)} documents via OpenRouter...")

    t0 = time.perf_counter()
    signals = parallel_extract_signals(docs, max_workers=10)
    elapsed = time.perf_counter() - t0

    print(f"\nExtracted {len(signals)} signals in {elapsed:.1f}s\n")
    for sig in signals:
        ev = sig.evidence[0] if sig.evidence else None
        snippet = ev.snippet[:100] if ev else ""
        print(
            f"  [{sig.event_type.value}] {sig.event_subtype} ({sig.severity.value}) "
            f"| doc={ev.document_id if ev else '?'} | {snippet!r}"
        )

    # Persist results for cache replay
    try:
        with output_path.open("w", encoding="utf-8") as f:
            for sig in signals:
                f.write(json.dumps(sig.model_dump(mode="json")) + "\n")
        print(f"\nSaved {len(signals)} signals to: {output_path}")
    except Exception as exc:
        print(f"\nFailed to save results: {exc!r}")


if __name__ == "__main__":
    main()
