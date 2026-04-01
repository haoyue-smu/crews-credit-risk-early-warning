"""SQLite database session management."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from shared.config import settings

# Default to SQLite in the data/ directory
_db_url = settings.database_url or "sqlite:///./data/ubs_credit.db"

# Ensure the data directory exists
if _db_url.startswith("sqlite:///./"):
    data_dir = os.path.dirname(_db_url.replace("sqlite:///./", "./"))
    os.makedirs(data_dir or "data", exist_ok=True)

engine = create_engine(_db_url, connect_args={"check_same_thread": False} if "sqlite" in _db_url else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables if they don't exist."""
    from backend.services.db.models import Base
    Base.metadata.create_all(bind=engine)
