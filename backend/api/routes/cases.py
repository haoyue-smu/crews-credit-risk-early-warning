"""Case management API routes.

Endpoints:
  POST /api/cases              — Create a new case
  GET  /api/cases              — List all cases
  GET  /api/cases/{id}         — Get case details
  GET  /api/cases/{id}/status  — Status polling (lightweight)
  GET  /api/cases/{id}/result  — Full result JSON
  POST /api/cases/{id}/documents — Upload financial documents
  POST /api/cases/{id}/run-fis — Kick off FIS graph
  POST /api/cases/{id}/run-rs  — Kick off RS graph
  POST /api/cases/{id}/run-sis — Kick off SIS graph
  POST /api/cases/{id}/run-frd — Kick off FRD graph
  POST /api/cases/{id}/run-all — Run FIS → RS → SIS → FRD sequentially
"""

import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.services.db.session import get_db
from backend.services.db import crud
from backend.services.graph_runner import run_fis_graph, run_rs_graph, run_sis_graph, run_frd_graph, run_full_pipeline
from shared.states.case_state import (
    CaseState,
    CompanyProfile,
    UploadedFinancialDocument,
)

router = APIRouter()

# Upload directory
UPLOAD_DIR = os.path.join("data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class CreateCaseRequest(BaseModel):
    company_name: str
    company_type: str = "private"   # "public" | "private"
    jurisdiction: Optional[str] = None
    ticker: Optional[str] = None
    isin: Optional[str] = None
    website: Optional[str] = None
    industry_sector: Optional[str] = None
    is_manufacturing: bool = False
    market_cap: Optional[float] = None


class CaseStatusResponse(BaseModel):
    case_id: str
    status: str
    company_name: str
    warnings: list[str]
    errors: list[str]
    created_at: str
    updated_at: str
    audit_log_count: int
    frd_traffic_light: Optional[str] = None


class CaseListItem(BaseModel):
    case_id: str
    company_name: str
    status: str
    created_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/cases", response_model=CaseStatusResponse)
def create_case(req: CreateCaseRequest, db: Session = Depends(get_db)):
    """Create a new credit analysis case."""
    case_id = f"case-{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow()

    case = CaseState(
        case_id=case_id,
        created_at=now,
        updated_at=now,
        company=CompanyProfile(
            company_id=f"comp-{uuid.uuid4().hex[:6]}",
            company_name=req.company_name,
            company_type=req.company_type,
            jurisdiction=req.jurisdiction,
            ticker=req.ticker,
            isin=req.isin,
            website=req.website,
            industry_sector=req.industry_sector,
            is_manufacturing=req.is_manufacturing,
            market_cap=req.market_cap,
        ),
    )

    crud.create_case(db, case)

    return CaseStatusResponse(
        case_id=case_id,
        status=case.status,
        company_name=case.company.company_name,
        warnings=case.warnings,
        errors=case.errors,
        created_at=case.created_at.isoformat(),
        updated_at=case.updated_at.isoformat(),
        audit_log_count=0,
    )


@router.get("/cases", response_model=list[CaseListItem])
def list_cases(db: Session = Depends(get_db)):
    """List all cases."""
    records = crud.list_cases(db)
    return [
        CaseListItem(
            case_id=r.case_id,
            company_name=r.company_name,
            status=r.status,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in records
    ]


@router.get("/cases/{case_id}/status", response_model=CaseStatusResponse)
def get_case_status(case_id: str, db: Session = Depends(get_db)):
    """Lightweight status poll."""
    case = crud.get_case_state(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    return CaseStatusResponse(
        case_id=case.case_id,
        status=case.status,
        company_name=case.company.company_name,
        warnings=case.warnings,
        errors=case.errors,
        created_at=case.created_at.isoformat(),
        updated_at=case.updated_at.isoformat(),
        audit_log_count=len(case.audit_log),
        frd_traffic_light=case.frd_traffic_light,
    )


@router.get("/cases/{case_id}/result")
def get_case_result(case_id: str, db: Session = Depends(get_db)):
    """Full result JSON — includes financial features, retrieval results, audit log."""
    case = crud.get_case_state(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    return case.model_dump(mode="json")


@router.post("/cases/{case_id}/documents")
async def upload_document(
    case_id: str,
    file: UploadFile = File(...),
    document_role: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a financial document (XML, XBRL, or PDF)."""
    case = crud.get_case_state(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    # Validate file type
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("xml", "xbrl", "pdf"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{ext}. Accepted: .xml, .xbrl, .pdf"
        )

    # Save file to disk
    doc_id = f"doc-{uuid.uuid4().hex[:8]}"
    case_upload_dir = os.path.join(UPLOAD_DIR, case_id)
    os.makedirs(case_upload_dir, exist_ok=True)
    local_path = os.path.join(case_upload_dir, filename)

    content = await file.read()
    with open(local_path, "wb") as f:
        f.write(content)

    # Update case state
    doc = UploadedFinancialDocument(
        document_id=doc_id,
        filename=filename,
        file_type=ext,
        local_path=os.path.abspath(local_path),
        uploaded_at=datetime.utcnow(),
        document_role=document_role if document_role in ("annual_report", "quarterly_report") else None,
    )
    case.uploaded_financial_documents.append(doc)
    case.updated_at = datetime.utcnow()
    crud.update_case(db, case_id, case)

    # Also track in uploaded_files table
    crud.save_uploaded_file(db, case_id, doc_id, filename, ext, os.path.abspath(local_path))

    return {
        "document_id": doc_id,
        "filename": filename,
        "file_type": ext,
        "case_id": case_id,
        "total_documents": len(case.uploaded_financial_documents),
    }


@router.post("/cases/{case_id}/run-fis")
def trigger_fis(
    case_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Kick off FIS graph as a background task."""
    case = crud.get_case_state(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not case.uploaded_financial_documents:
        raise HTTPException(status_code=400, detail="No documents uploaded. Upload at least one file first.")

    background_tasks.add_task(run_fis_graph, case_id)
    return {"case_id": case_id, "action": "fis_started", "status": "running"}


@router.post("/cases/{case_id}/run-rs")
def trigger_rs(
    case_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Kick off RS graph as a background task."""
    case = crud.get_case_state(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    background_tasks.add_task(run_rs_graph, case_id)
    return {"case_id": case_id, "action": "rs_started", "status": "running"}


@router.post("/cases/{case_id}/run-sis")
def trigger_sis(
    case_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Kick off SIS graph as a background task."""
    case = crud.get_case_state(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    background_tasks.add_task(run_sis_graph, case_id)
    return {"case_id": case_id, "action": "sis_started", "status": "running"}


@router.post("/cases/{case_id}/run-frd")
def trigger_frd(
    case_id: str,
    background_tasks: BackgroundTasks,
    skip_report: bool = False,
    db: Session = Depends(get_db),
):
    """Kick off FRD graph as a background task. Pass ?skip_report=true to omit narrative generation."""
    case = crud.get_case_state(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not case.sis_output:
        raise HTTPException(status_code=400, detail="No SIS output available. Run SIS first.")

    background_tasks.add_task(run_frd_graph, case_id, skip_report)
    return {"case_id": case_id, "action": "frd_started", "status": "running"}


@router.post("/cases/{case_id}/run-all")
def trigger_full_pipeline(
    case_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Run FIS → RS → SIS → FRD sequentially as a background task."""
    case = crud.get_case_state(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not case.uploaded_financial_documents:
        raise HTTPException(status_code=400, detail="No documents uploaded.")

    background_tasks.add_task(run_full_pipeline, case_id)
    return {"case_id": case_id, "action": "full_pipeline_started", "status": "running"}
