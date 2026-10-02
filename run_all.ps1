# EcoMotorTwin - One-click startup script (PowerShell)
# Usage: .\run_all.ps1

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " EcoMotorTwin - Four-Motor Digital Twin" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[OK] Python found: $pythonVersion"
} catch {
    Write-Host "[ERROR] Python not found. Please install Python 3.12+" -ForegroundColor Red
    exit 1
}

# Create venv if missing
if (-not (Test-Path ".venv")) {
    Write-Host "[1/6] Creating Python virtual environment..."
    python -m venv .venv
} else {
    Write-Host "[1/6] Virtual environment exists."
}

# Install requirements
Write-Host "[2/6] Installing Python dependencies..."
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet

# Install frontend dependencies
Write-Host "[3/6] Installing frontend dependencies..."
Set-Location "frontend"
& npm.cmd install --silent
Set-Location ".."

# Generate data if missing
if (-not (Test-Path "data\motor_data.csv")) {
    Write-Host "[4/6] Generating training data..."
    & ".venv\Scripts\python.exe" -m backend.app.simulator.simulator
} else {
    Write-Host "[4/6] Training data exists."
}

# Train models if missing
if (-not (Test-Path "models_ml\fault_classifier.joblib")) {
    Write-Host "[5/6] Training AI models..."
    & ".venv\Scripts\python.exe" -m backend.app.ai.train
} else {
    Write-Host "[5/6] AI models exist."
}

# Start services
Write-Host "[6/6] Starting services..."
Write-Host ""
Write-Host "Starting API server on http://localhost:8000" -ForegroundColor Green
Start-Process -FilePath "cmd" -ArgumentList "/c", ".venv\Scripts\python.exe -m backend.app.main" -WindowStyle Normal

Start-Sleep -Seconds 3

Write-Host "Starting frontend on http://localhost:5173" -ForegroundColor Green
Start-Process -FilePath "cmd" -ArgumentList "/c", "cd frontend && npm.cmd run dev" -WindowStyle Normal

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " EcoMotorTwin is starting!" -ForegroundColor Cyan
Write-Host ""
Write-Host " API:      http://localhost:8000" -ForegroundColor Yellow
Write-Host " API Docs: http://localhost:8000/docs" -ForegroundColor Yellow
Write-Host " Frontend: http://localhost:5173" -ForegroundColor Yellow
Write-Host ""
Write-Host " Press Ctrl+C in each window to stop." -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Cyan

# Open browser
Start-Sleep -Seconds 5
Start-Process "http://localhost:5173"
