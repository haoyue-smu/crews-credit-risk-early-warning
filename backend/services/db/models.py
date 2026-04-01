"""SQLAlchemy models for SQLite persistence."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class CaseRecord(Base):
    """Persisted case record — stores the full CaseState JSON."""
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(64), unique=True, nullable=False, index=True)
    company_name = Column(String(256), nullable=False)
    company_type = Column(String(16), nullable=False)
    industry_sector = Column(String(128), nullable=True)
    status = Column(String(64), nullable=False, default="created")
    case_json = Column(Text, nullable=False)  # Full CaseState serialized
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UploadedFileRecord(Base):
    """Track uploaded files on disk."""
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(64), nullable=False, index=True)
    document_id = Column(String(64), nullable=False)
    filename = Column(String(512), nullable=False)
    file_type = Column(String(16), nullable=False)
    local_path = Column(String(1024), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
