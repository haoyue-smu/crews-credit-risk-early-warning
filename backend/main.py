"""FastAPI application entry point.

Includes:
  - CORS middleware for Streamlit frontend
  - Lifespan handler to initialize SQLite tables on startup
  - Case management API routes mounted at /api
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.cases import router as cases_router
from backend.services.db.session import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize database tables on startup."""
    init_db()
    logger.info("SQLite tables initialized.")
    yield


app = FastAPI(
    title="UBS Credit Assessment API",
    description=(
        "Agentic credit analysis platform — "
        "FIS (Financial Ingestion) + RS (Retrieval) + "
        "SIS (Signal Sourcing) + FRD (Fusion & Risk Decisioning) "
        "subgraphs via LangGraph."
    ),
    version="0.3.0",
    lifespan=lifespan,
)

# CORS — allow Streamlit (port 8501) and any local dev origin.
# Restrict allow_origins in production to your frontend URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases_router, prefix="/api")


@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "service": "UBS Credit Assessment API", "version": "0.3.0"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "healthy"}
