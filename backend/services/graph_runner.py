"""Async graph runner — runs FIS or RS graph as a background task.

Invokes the LangGraph, updates SQLite on completion/failure.
Used by FastAPI background tasks.
"""

import asyncio
import traceback
from datetime import datetime

from sqlalchemy.orm import Session

from backend.services.db.session import SessionLocal
from backend.services.db import crud
from shared.states.case_state import CaseState


def _get_db() -> Session:
    return SessionLocal()


def run_fis_graph(case_id: str):
    """Run the FIS subgraph synchronously (for BackgroundTasks)."""
    from orchestration.fis.graph import build_fis_graph

    db = _get_db()
    try:
        # Load current case state
        case = crud.get_case_state(db, case_id)
        if case is None:
            print(f"[GraphRunner] Case {case_id} not found")
            return

        # Update status to running
        case.status = "fis_running"
        case.updated_at = datetime.utcnow()
        crud.update_case(db, case_id, case)

        # Build and invoke graph
        graph = build_fis_graph()
        result = graph.invoke({"case": case})
        updated_case: CaseState = result["case"]

        # Persist result
        crud.update_case(db, case_id, updated_case)
        print(f"[GraphRunner] FIS complete for {case_id}: {updated_case.status}")

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[GraphRunner] FIS failed for {case_id}: {e}\n{tb}")
        try:
            case = crud.get_case_state(db, case_id)
            if case:
                case.status = "fis_error"
                case.errors.append(f"FIS graph failed: {str(e)}")
                case.updated_at = datetime.utcnow()
                crud.update_case(db, case_id, case)
        except Exception:
            pass
    finally:
        db.close()


def run_rs_graph(case_id: str):
    """Run the RS subgraph (async nodes, but called from sync background task)."""
    from orchestration.rs.graph import build_rs_graph

    db = _get_db()
    try:
        case = crud.get_case_state(db, case_id)
        if case is None:
            print(f"[GraphRunner] Case {case_id} not found")
            return

        case.status = "rs_running"
        case.updated_at = datetime.utcnow()
        crud.update_case(db, case_id, case)

        graph = build_rs_graph()

        # RS uses async nodes — need to run in event loop
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
        print(f"[GraphRunner] RS complete for {case_id}: {updated_case.status}")

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[GraphRunner] RS failed for {case_id}: {e}\n{tb}")
        try:
            case = crud.get_case_state(db, case_id)
            if case:
                case.status = "rs_error"
                case.errors.append(f"RS graph failed: {str(e)}")
                case.updated_at = datetime.utcnow()
                crud.update_case(db, case_id, case)
        except Exception:
            pass
    finally:
        db.close()


def run_full_pipeline(case_id: str):
    """Run FIS → RS sequentially."""
    run_fis_graph(case_id)
    # Only proceed to RS if FIS succeeded
    db = _get_db()
    try:
        case = crud.get_case_state(db, case_id)
        if case and case.status == "fis_features_extracted":
            db.close()
            run_rs_graph(case_id)
        else:
            print(f"[GraphRunner] Skipping RS — FIS status: {case.status if case else 'not found'}")
    except Exception:
        pass
    finally:
        if db:
            db.close()
