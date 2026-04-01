"""CRUD helpers for case persistence."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.services.db.models import CaseRecord, UploadedFileRecord
from shared.states.case_state import CaseState


def create_case(db: Session, case: CaseState) -> CaseRecord:
    """Insert a new case record."""
    record = CaseRecord(
        case_id=case.case_id,
        company_name=case.company.company_name,
        company_type=case.company.company_type,
        industry_sector=case.company.industry_sector,
        status=case.status,
        case_json=case.model_dump_json(),
        created_at=case.created_at,
        updated_at=case.updated_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_case(db: Session, case_id: str) -> Optional[CaseRecord]:
    """Retrieve a case by case_id."""
    return db.query(CaseRecord).filter(CaseRecord.case_id == case_id).first()


def get_case_state(db: Session, case_id: str) -> Optional[CaseState]:
    """Retrieve the full CaseState by case_id."""
    record = get_case(db, case_id)
    if record is None:
        return None
    return CaseState.model_validate_json(record.case_json)


def update_case(db: Session, case_id: str, case: CaseState) -> Optional[CaseRecord]:
    """Update an existing case record with new CaseState."""
    record = get_case(db, case_id)
    if record is None:
        return None
    record.status = case.status
    record.case_json = case.model_dump_json()
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return record


def update_case_status(db: Session, case_id: str, status: str) -> Optional[CaseRecord]:
    """Update only the status field of a case."""
    record = get_case(db, case_id)
    if record is None:
        return None
    record.status = status
    record.updated_at = datetime.utcnow()
    db.commit()
    return record


def list_cases(db: Session, limit: int = 50) -> list[CaseRecord]:
    """List all cases, most recent first."""
    return db.query(CaseRecord).order_by(CaseRecord.created_at.desc()).limit(limit).all()


def save_uploaded_file(db: Session, case_id: str, document_id: str,
                       filename: str, file_type: str, local_path: str) -> UploadedFileRecord:
    """Track an uploaded file."""
    record = UploadedFileRecord(
        case_id=case_id,
        document_id=document_id,
        filename=filename,
        file_type=file_type,
        local_path=local_path,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
