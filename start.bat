@echo off
cd /d "%~dp0"

echo Starting UBS Credit Assessment...
echo.

:: Start backend in a new window
start "Backend (FastAPI)" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000 --reload"

:: Wait a moment for backend to initialise
timeout /t 3 /nobreak >nul

:: Start frontend in a new window
start "Frontend (Streamlit)" cmd /k ".venv\Scripts\python.exe -m streamlit run frontend\app\main.py"

echo Backend running at http://localhost:8000
echo Frontend running at http://localhost:8501
echo.
echo Close the Backend and Frontend windows to stop the servers.
