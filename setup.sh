@echo off
REM Setup script for Drive Chatbot

echo ========================================
echo Drive Chatbot Setup
echo ========================================
echo.

echo Step 1: Installing Python dependencies...
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install Python dependencies
    pause
    exit /b 1
)

echo.
echo Step 2: Installing frontend dependencies...
cd frontend
call npm install
if errorlevel 1 (
    echo ERROR: Failed to install frontend dependencies
    pause
    exit /b 1
)

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo To run the application:
echo.
echo Terminal 1 (Backend):
echo   cd chat-ambildata
echo   python -m uvicorn app:app --reload --port 8000
echo.
echo Terminal 2 (Frontend):
echo   cd chat-ambildata/frontend
echo   npm run dev
echo.
echo Then open: http://localhost:3000
echo.
pause
