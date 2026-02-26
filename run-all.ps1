# Drive Chatbot - Auto Setup & Run Script
# Run this script as Administrator

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Drive Chatbot - Auto Setup & Run" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Function to check if command exists
function Test-CommandExists {
    param($command)
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'stop'
    try {
        if (Get-Command $command) { return $true }
    }
    catch { return $false }
    finally { $ErrorActionPreference = $oldPreference }
}

# Function to install Python
function Install-Python {
    Write-Host "Python not found. Installing Python 3.12..." -ForegroundColor Yellow
    Write-Host ""

    if (Test-CommandExists winget) {
        Write-Host "Using winget to install Python..." -ForegroundColor Green
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements

        Write-Host ""
        Write-Host "Python installed! Please REFRESH your environment variables by:" -ForegroundColor Yellow
        Write-Host "  1. Closing this terminal" -ForegroundColor White
        Write-Host "  2. Opening a NEW terminal as Administrator" -ForegroundColor White
        Write-Host "  3. Running this script again" -ForegroundColor White
        Write-Host ""
        Write-Host "Press any key to exit..." -ForegroundColor Red
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        exit
    }
    else {
        Write-Host "winget not found. Please install Python manually:" -ForegroundColor Red
        Write-Host "1. Visit: https://www.python.org/downloads/" -ForegroundColor White
        Write-Host "2. Download Python 3.12.x" -ForegroundColor White
        Write-Host "3. Make sure to CHECK 'Add Python to PATH'" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Press any key to exit..." -ForegroundColor Red
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        exit
    }
}

# Check Python
Write-Host "Step 1: Checking Python installation..." -ForegroundColor Cyan
if (-not (Test-CommandExists python)) {
    Install-Python
}

# Show Python version
$pythonVersion = python --version 2>&1
Write-Host "Found: $pythonVersion" -ForegroundColor Green
Write-Host ""

# Check Node.js
Write-Host "Step 2: Checking Node.js installation..." -ForegroundColor Cyan
if (-not (Test-CommandExists node)) {
    Write-Host "Node.js not found. Installing..." -ForegroundColor Yellow
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
}
$nodeVersion = node --version
$npmVersion = npm --version
Write-Host "Found: Node $nodeVersion, npm $npmVersion" -ForegroundColor Green
Write-Host ""

# Set project directory
$projectDir = "C:\Users\777701260014\drive-chatbot\chat-ambildata"
Set-Location $projectDir

# Install Python dependencies
Write-Host "Step 3: Installing Python dependencies..." -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if ($LASTEXITCODE -eq 0) {
    Write-Host "Python dependencies installed successfully!" -ForegroundColor Green
} else {
    Write-Host "Failed to install Python dependencies" -ForegroundColor Red
    pause
    exit
}
Write-Host ""

# Install frontend dependencies
Write-Host "Step 4: Installing frontend dependencies..." -ForegroundColor Cyan
Set-Location "$projectDir\frontend"
npm install
if ($LASTEXITCODE -eq 0) {
    Write-Host "Frontend dependencies installed successfully!" -ForegroundColor Green
} else {
    Write-Host "Failed to install frontend dependencies" -ForegroundColor Red
    pause
    exit
}
Write-Host ""

# Build frontend for production
Write-Host "Step 5: Building frontend..." -ForegroundColor Cyan
npm run build
if ($LASTEXITCODE -eq 0) {
    Write-Host "Frontend built successfully!" -ForegroundColor Green
} else {
    Write-Host "Frontend build failed (continuing anyway)" -ForegroundColor Yellow
}
Write-Host ""

# Start backend
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup Complete! Starting servers..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Backend will start on: http://localhost:8000" -ForegroundColor Yellow
Write-Host "Frontend will start on: http://localhost:3000" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop the servers" -ForegroundColor White
Write-Host ""

# Start backend server
Set-Location $projectDir
Write-Host "Starting backend server..." -ForegroundColor Cyan
Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "app:app", "--reload", "--port", "8000" -NoNewWindow

# Wait a moment for backend to start
Start-Sleep -Seconds 3

# Start frontend server
Set-Location "$projectDir\frontend"
Write-Host "Starting frontend server..." -ForegroundColor Cyan
Start-Process -FilePath "npm" -ArgumentList "run", "dev" -NoNewWindow

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Both servers are running!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Open your browser and go to:" -ForegroundColor Cyan
Write-Host "  http://localhost:3000" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C in this terminal to stop both servers" -ForegroundColor White
Write-Host ""

# Keep script running
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host ""
    Write-Host "Stopping servers..." -ForegroundColor Yellow
    Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Host "Servers stopped." -ForegroundColor Green
}
