"""Development script to run SIS LangExtract extraction on local Hyflux data.

Run with:
    python -m orchestration.sis.run_extraction

This is intentionally simple and suitable for Phase 2 development/testing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable
import time

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


def main() -> None:
    """Execute local extraction for Hyflux documents."""
    try:
        import langextract as lx  # type: ignore
    except ModuleNotFoundError:
        print(
            "langextract is not installed. Install it first: "
            "`pip install langextract`"
        )
        return

    project_root = Path(__file__).resolve().parents[2]
    hyflux_dir = project_root / "data" / "local" / "hyflux"
    output_path = hyflux_dir / "extraction_results.jsonl"

    load_dotenv()
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        print("Missing GEMINI_API_KEY in .env (required for LangExtract/Gemini).")
        return

    # LangExtract uses LANGEXTRACT_API_KEY as the unified environment variable.
    os.environ["LANGEXTRACT_API_KEY"] = gemini_api_key

    # Few-shot examples + prompt description.
    EXAMPLES = get_sis_example_data()

    results: list[Any] = []
    for path, doc in _iter_hyflux_documents(hyflux_dir):
        label = path.name
        print(f"\nValid document: {label} (company_id={doc.company_id}, source_type={doc.source_type})")

        try:
            result = lx.extract(
                text_or_documents=doc.full_text,
                prompt_description=EXTRACTION_PROMPT,
                examples=EXAMPLES,
                model_id="gemini-2.5-flash",
                extraction_passes=1,
                max_workers=1,
            )

            results.append(result)
            _print_raw_result(label, result)
        except Exception as exc:
            print(f"Extraction failed for {label}: {exc!r}")
            continue

        print("Waiting 15s for rate limit...")
        time.sleep(15)

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

