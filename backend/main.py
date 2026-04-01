"""FastAPI application entry point.

Includes:
  - CORS middleware for Streamlit frontend
  - Lifespan handler to initialize SQLite tables
  - Case management API routes
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.cases import router as cases_router
from backend.services.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup."""
    init_db()
    print("[Backend] SQLite tables initialized.")
    yield


app = FastAPI(
    title="UBS Credit Assessment API",
    description="Agentic credit analysis platform — FIS + RS subgraphs via LangGraph",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — allow Streamlit (typically port 8501) and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(cases_router, prefix="/api")


@app.get("/")
def root():
    return {"status": "ok", "service": "UBS Credit Assessment API", "version": "0.2.0"}


@app.get("/health")
def health():
    return {"status": "healthy"}
