"""Async graph runner — runs FIS, RS, SIS, or FRD as a background task.

Each public function loads the CaseState from SQLite, invokes the appropriate
LangGraph subgraph synchronously, then writes the result back to SQLite.

These functions are designed to be called by FastAPI BackgroundTasks, which run
outside the request context. Each function therefore opens and closes its own
database session rather than depending on the request-scoped `get_db` dependency.

Pipeline order (run_full_pipeline chains all four):
  FIS → RS → SIS → FRD
"""

import asyncio
import logging
import traceback
from datetime import datetime

from sqlalchemy.orm import Session

from backend.services.db.session import SessionLocal
from backend.services.db import crud
from shared.states.case_state import CaseState
from shared.states.frd_bridge import normalized_documents_to_pipeline_docs, financial_features_to_profile

logger = logging.getLogger(__name__)


def _get_db() -> Session:
    return SessionLocal()


# ---------------------------------------------------------------------------
# FIS
# ---------------------------------------------------------------------------

def run_fis_graph(case_id: str) -> None:
    """Run the FIS subgraph synchronously (for BackgroundTasks).

    Reads uploaded financial documents from CaseState, parses them with
    an LLM, and deterministically computes ratios + Altman Z-Score.

    Terminal statuses:  fis_features_extracted | fis_error | fis_ingestion_skipped
    """
    from orchestration.fis.graph import build_fis_graph

    db = _get_db()
    try:
        case = crud.get_case_state(db, case_id)
        if case is None:
            logger.warning("FIS: case %s not found", case_id)
            return

        case.status = "fis_running"
        case.updated_at = datetime.utcnow()
        crud.update_case(db, case_id, case)

        graph = build_fis_graph()
        result = graph.invoke({"case": case})
        updated_case: CaseState = result["case"]

        crud.update_case(db, case_id, updated_case)
        logger.info("FIS complete for %s: %s", case_id, updated_case.status)

    except Exception as e:
        logger.error("FIS failed for %s: %s\n%s", case_id, e, traceback.format_exc())
        try:
            case = crud.get_case_state(db, case_id)
            if case:
                case.status = "fis_error"
                case.errors.append(f"FIS graph failed: {e}")
                case.updated_at = datetime.utcnow()
                crud.update_case(db, case_id, case)
        except Exception:
            logger.exception("FIS: could not write error status for %s", case_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# RS
# ---------------------------------------------------------------------------

def run_rs_graph(case_id: str) -> None:
    """Run the RS subgraph (async nodes, invoked from a sync background task).

    Generates Tavily search queries, executes them in parallel, deduplicates
    and scores results, then checks topic coverage with a retry loop.

    Terminal statuses:  rs_complete | rs_error
    """
    from orchestration.rs.graph import build_rs_graph

    db = _get_db()
    try:
        case = crud.get_case_state(db, case_id)
        if case is None:
            logger.warning("RS: case %s not found", case_id)
            return

        case.status = "rs_running"
        case.updated_at = datetime.utcnow()
        crud.update_case(db, case_id, case)

        graph = build_rs_graph()

        # RS graph nodes are async; run them in a fresh event loop because
        # FastAPI BackgroundTasks run in the same thread as the ASGI server
        # and there may already be a running loop.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                graph.ainvoke({"case": case, "retrieved_items_buffer": [], "_rs_coverage": None})
            )
        finally:
            loop.close()

        updated_case: CaseState = result["case"]
        crud.update_case(db, case_id, updated_case)
        logger.info("RS complete for %s: %s", case_id, updated_case.status)

    except Exception as e:
        logger.error("RS failed for %s: %s\n%s", case_id, e, traceback.format_exc())
        try:
            case = crud.get_case_state(db, case_id)
            if case:
                case.status = "rs_error"
                case.errors.append(f"RS graph failed: {e}")
                case.updated_at = datetime.utcnow()
                crud.update_case(db, case_id, case)
        except Exception:
            logger.exception("RS: could not write error status for %s", case_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# SIS
# ---------------------------------------------------------------------------

def run_sis_graph(case_id: str) -> None:
    """Run the SIS subgraph (synchronous LangGraph, PipelineState).

    Bridges RS output: CaseState.normalized_documents → PipelineState['documents'],
    invokes the extract → validate → verify → conflict → evidence_gate pipeline,
    then writes sis_output back to CaseState.

    Terminal statuses:  sis_complete | sis_error | sis_skipped_no_docs
    """
    from orchestration.sis.graph import build_sis_graph

    db = _get_db()
    try:
        case = crud.get_case_state(db, case_id)
        if case is None:
            logger.warning("SIS: case %s not found", case_id)
            return

        if not case.normalized_documents:
            logger.info("SIS skipped for %s — no normalized documents from RS", case_id)
            case.status = "sis_skipped_no_docs"
            case.warnings.append("SIS skipped: no normalized documents from RS.")
            case.updated_at = datetime.utcnow()
            crud.update_case(db, case_id, case)
            return

        case.status = "sis_running"
        case.updated_at = datetime.utcnow()
        crud.update_case(db, case_id, case)

        # Bridge: serialize CaseState.normalized_documents into the flat dict
        # format that PipelineState['documents'] expects.
        pipeline_state = {
            "company_id": case.company.company_id,
            "documents": normalized_documents_to_pipeline_docs(case),
        }

        graph = build_sis_graph()
        result = graph.invoke(pipeline_state)

        sis_output = result.get("sis_output")
        case = crud.get_case_state(db, case_id)  # re-load for freshness
        case.sis_output = sis_output
        case.status = "sis_complete"
        case.updated_at = datetime.utcnow()
        crud.update_case(db, case_id, case)

        signals_n = len(sis_output.get("signals", [])) if sis_output else 0
        logger.info("SIS complete for %s: %d signals extracted", case_id, signals_n)

    except Exception as e:
        logger.error("SIS failed for %s: %s\n%s", case_id, e, traceback.format_exc())
        try:
            case = crud.get_case_state(db, case_id)
            if case:
                case.status = "sis_error"
                case.errors.append(f"SIS graph failed: {e}")
                case.updated_at = datetime.utcnow()
                crud.update_case(db, case_id, case)
        except Exception:
            logger.exception("SIS: could not write error status for %s", case_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# FRD
# ---------------------------------------------------------------------------

def run_frd_graph(case_id: str, skip_report: bool = False) -> None:
    """Run the FRD subgraph (synchronous LangGraph, PipelineState).

    Bridges SIS output + FIS FinancialFeatures → PipelineState, invokes the
    aggregate → score_risk → generate_report pipeline, then writes frd_output
    and frd_traffic_light back to CaseState.

    Parameters
    ----------
    skip_report:
        If True, the generate_report node is bypassed (no LLM narrative).
        Useful for quick scoring without paying for report generation.

    Terminal statuses:  frd_complete | frd_error | frd_skipped_no_sis
    """
    from orchestration.frd.graph import build_frd_graph

    db = _get_db()
    try:
        case = crud.get_case_state(db, case_id)
        if case is None:
            logger.warning("FRD: case %s not found", case_id)
            return

        if not case.sis_output:
            logger.info("FRD skipped for %s — no SIS output available", case_id)
            case.status = "frd_skipped_no_sis"
            case.warnings.append("FRD skipped: no SIS output available.")
            case.updated_at = datetime.utcnow()
            crud.update_case(db, case_id, case)
            return

        case.status = "frd_running"
        case.updated_at = datetime.utcnow()
        crud.update_case(db, case_id, case)

        # Bridge: build FinancialProfile dict from FIS output (may be None if
        # FIS was skipped or the Z-Score could not be computed).
        pipeline_state = {
            "sis_output": case.sis_output,
            "financial_profile": financial_features_to_profile(case),
            "skip_report": skip_report,
            "analyst_guidance": case.analyst_guidance or "",
        }

        graph = build_frd_graph()
        result = graph.invoke(pipeline_state)

        frd_output = result.get("frd_output")
        case = crud.get_case_state(db, case_id)  # re-load for freshness
        case.frd_output = frd_output
        case.frd_traffic_light = frd_output.get("traffic_light") if frd_output else None
        case.status = "frd_complete"
        case.updated_at = datetime.utcnow()
        crud.update_case(db, case_id, case)
        logger.info("FRD complete for %s: traffic_light=%s", case_id, case.frd_traffic_light)

    except Exception as e:
        logger.error("FRD failed for %s: %s\n%s", case_id, e, traceback.format_exc())
        try:
            case = crud.get_case_state(db, case_id)
            if case:
                case.status = "frd_error"
                case.errors.append(f"FRD graph failed: {e}")
                case.updated_at = datetime.utcnow()
                crud.update_case(db, case_id, case)
        except Exception:
            logger.exception("FRD: could not write error status for %s", case_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_full_pipeline(case_id: str) -> None:
    """Run FIS → RS → SIS → FRD sequentially.

    Each stage is only started if the previous stage completed successfully.
    Status is checked from the database between stages to pick up the authoritative
    value written by the preceding runner function.
    """
    run_fis_graph(case_id)

    db = _get_db()
    try:
        case = crud.get_case_state(db, case_id)
        if not (case and case.status == "fis_features_extracted"):
            logger.info(
                "Full pipeline: skipping RS — FIS status is '%s'",
                case.status if case else "not found",
            )
            return
    finally:
        db.close()

    run_rs_graph(case_id)

    db = _get_db()
    try:
        case = crud.get_case_state(db, case_id)
        if not (case and case.status == "rs_complete"):
            logger.info(
                "Full pipeline: skipping SIS — RS status is '%s'",
                case.status if case else "not found",
            )
            return
    finally:
        db.close()

    run_sis_graph(case_id)

    db = _get_db()
    try:
        case = crud.get_case_state(db, case_id)
        if not (case and case.status == "sis_complete"):
            logger.info(
                "Full pipeline: skipping FRD — SIS status is '%s'",
                case.status if case else "not found",
            )
            return
    finally:
        db.close()

    run_frd_graph(case_id)
