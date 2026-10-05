#!/usr/bin/env bash
# macOS/Linux equivalent of start.bat: runs the backend and frontend together.
# Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "No virtualenv found at .venv. Create it first:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "Starting CREWS (Credit Risk Early Warning System)..."

"$PY" -m uvicorn backend.main:app --port 8000 --reload &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM

# Give the backend a moment to initialise
sleep 3

echo "Backend running at http://localhost:8000"
echo "Frontend running at http://localhost:8501"
"$PY" -m streamlit run frontend/app/main.py
