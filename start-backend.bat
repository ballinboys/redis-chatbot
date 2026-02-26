@echo off
cd /d "%~dp0"
echo Starting Backend Server on port 8000...
python -m uvicorn app:app --reload --port 8000
pause
