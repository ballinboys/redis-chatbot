@echo off
REM Setup script for Drive Chatbot

echo ========================================
echo Drive Chatbot Setup
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.12+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

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
    echo Please make sure Node.js is installed from https://nodejs.org/
    pause
    exit /b 1
)

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo To run the application, open TWO terminals:
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
