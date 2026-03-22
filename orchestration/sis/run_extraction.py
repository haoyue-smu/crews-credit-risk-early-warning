"""Development script to run SIS LangExtract extraction on local Hyflux data.

Run with:
    python -m orchestration.sis.run_extraction

Uses document-level ``ThreadPoolExecutor(max_workers=10)`` plus per-call
``extraction_passes=2`` and ``max_workers=10`` for LangExtract/Gemini
(Paid Tier 1–appropriate throughput).

Pass ``--use-cache`` to skip API calls and replay cached ``extraction_results.jsonl``
(``--no-cache`` forces a fresh run).
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

from shared.schemas.documents import DocumentInput
from orchestration.sis.prompts.examples import get_sis_example_data
from orchestration.sis.prompts.templates import EXTRACTION_PROMPT


def _find_extraction_list(obj: Any) -> list[Any]:
    """Best-effort extraction list discovery for printing results."""
    if isinstance(obj, dict):
        # Common patterns: {"extractions": [...]}, {"result": {"extractions": [...]}}
        if isinstance(obj.get("extractions"), list):
            return obj["extractions"]
        for v in obj.values():
            found = _find_extraction_list(v)
            if found:
                return found
    if isinstance(obj, list):
        for item in obj:
            found = _find_extraction_list(item)
            if found:
                return found
    return []


def _print_raw_result(label: str, result: Any) -> None:
    """Print raw result plus extracted items (attributes + char intervals)."""
    print(f"\n=== {label} ===")
    print("Raw result:")
    print(result)

    extractions = _find_extraction_list(result)
    if not extractions:
        print("\n(No extraction list found in result; printed raw output only.)")
        return

    print("\nExtracted items (best-effort):")
    for i, ex in enumerate(extractions, start=1):
        if isinstance(ex, dict):
            attrs = ex.get("attributes", None)
            char_interval = ex.get("char_interval", ex.get("charInterval", None))
            print(f"- {i}. attributes={attrs} char_interval={char_interval}")
        else:
            print(f"- {i}. {ex}")


def _iter_hyflux_documents(hyflux_dir: Path) -> Iterable[tuple[Path, DocumentInput]]:
    """Load and validate all *.json docs under a directory."""
    for path in sorted(hyflux_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        doc = DocumentInput.model_validate(payload)
        yield path, doc


def _run_cache_mode(hyflux_dir: Path, output_path: Path) -> None:
    """Print cached JSONL the same way as a live run; do not call the API or save."""
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
            text = str(payload.get("text", ""))
            label = text_to_label.get(text) or str(payload.get("document_id", "unknown"))
            _print_raw_result(label, payload)

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

    try:
        import langextract as lx  # type: ignore
    except ModuleNotFoundError:
        print(
            "langextract is not installed. Install it first: "
            "`pip install langextract`"
        )
        return

    load_dotenv()
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        print("Missing GEMINI_API_KEY in .env (required for LangExtract/Gemini).")
        return

    # LangExtract uses LANGEXTRACT_API_KEY as the unified environment variable.
    os.environ["LANGEXTRACT_API_KEY"] = gemini_api_key

    EXAMPLES = get_sis_example_data()
    doc_items: list[tuple[Path, DocumentInput]] = list(_iter_hyflux_documents(hyflux_dir))

    def _extract_one(idx: int, path: Path, doc: DocumentInput) -> tuple[int, str, Any, float, Exception | None]:
        """Run LangExtract for one document; return (index, label, result, seconds, error)."""
        label = path.name
        t0 = time.perf_counter()
        try:
            result = lx.extract(
                text_or_documents=doc.full_text,
                prompt_description=EXTRACTION_PROMPT,
                examples=EXAMPLES,
                model_id="gemini-2.5-flash",
                extraction_passes=2,
                max_workers=10,
            )
            elapsed = time.perf_counter() - t0
            return (idx, label, result, elapsed, None)
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            return (idx, label, None, elapsed, exc)

    results: list[Any] = []
    batch_t0 = time.perf_counter()

    if not doc_items:
        print(f"No *.json documents found under {hyflux_dir}")
        print(f"\nTotal wall-clock time: {time.perf_counter() - batch_t0:.1f}s")
        return

    for path, doc in doc_items:
        print(
            f"\nValid document: {path.name} (company_id={doc.company_id}, source_type={doc.source_type})"
        )

    print(f"\nExtracting {len(doc_items)} documents with up to 10 parallel workers...")

    completed_rows: list[tuple[int, str, Any, float, Exception | None]] = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_idx = {
            executor.submit(_extract_one, idx, path, doc): idx
            for idx, (path, doc) in enumerate(doc_items)
        }
        for fut in as_completed(future_to_idx):
            completed_rows.append(fut.result())

    for idx, label, result, elapsed, err in sorted(completed_rows, key=lambda r: r[0]):
        if err is not None:
            print(f"{label} completed in {elapsed:.1f}s (failed: {err!r})")
            continue
        print(f"{label} completed in {elapsed:.1f}s")
        results.append(result)
        _print_raw_result(label, result)

    batch_elapsed = time.perf_counter() - batch_t0
    print(f"\nTotal wall-clock time: {batch_elapsed:.1f}s")

    # Persist results for interactive visualization / debugging.
    try:
        lx.io.save_annotated_documents(
            results,
            output_name=output_path.name,
            output_dir=str(output_path.parent),
        )
        print(f"\nSaved annotated extraction results to: {output_path}")
    except Exception as exc:
        print(f"\nFailed to save annotated documents: {exc!r}")


if __name__ == "__main__":
    main()
