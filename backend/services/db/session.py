"""SQLite database session management.

Provides:
  get_db()  — FastAPI dependency that yields a SQLAlchemy Session and
              commits on success or rolls back on error.
  init_db() — Creates all tables from the SQLAlchemy metadata (run at startup).

The DATABASE_URL setting defaults to SQLite. To switch to PostgreSQL, set
  DATABASE_URL=postgresql://user:pass@host/dbname
in your .env file. The check_same_thread argument is only passed for SQLite.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from shared.config import settings

_db_url = settings.database_url or "sqlite:///./data/crews.db"

# Ensure the data/ directory exists for SQLite
if _db_url.startswith("sqlite:///./"):
    _data_dir = os.path.dirname(_db_url.replace("sqlite:///./", "./"))
    os.makedirs(_data_dir or "data", exist_ok=True)

_connect_args = {"check_same_thread": False} if "sqlite" in _db_url else {}
engine = create_engine(_db_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency that yields a database session.

    Commits on clean exit; rolls back and re-raises on any exception.
    Always closes the session in the finally block.
    """
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create all SQLAlchemy-defined tables if they do not already exist."""
    from backend.services.db.models import Base
    Base.metadata.create_all(bind=engine)
