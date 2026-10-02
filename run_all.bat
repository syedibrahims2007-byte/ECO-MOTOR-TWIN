@echo off
REM EcoMotorTwin - One-click startup script
REM Usage: run_all.bat

setlocal EnableDelayedExpansion

echo ============================================
echo  EcoMotorTwin - Four-Motor Digital Twin
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.12+
    pause
    exit /b 1
)

REM Create venv if missing
if not exist ".venv" (
    echo [1/6] Creating Python virtual environment...
    python -m venv .venv
) else (
    echo [1/6] Virtual environment exists.
)

REM Install requirements
echo [2/6] Installing Python dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
call deactivate

REM Install frontend dependencies
echo [3/6] Installing frontend dependencies...
cd frontend
call npm.cmd install --silent
cd ..

REM Generate data if missing
if not exist "data\motor_data.csv" (
    echo [4/6] Generating training data...
    call .venv\Scripts\activate.bat
    python -m backend.app.simulator.simulator
    call deactivate
) else (
    echo [4/6] Training data exists.
)

REM Train models if missing
if not exist "models_ml\fault_classifier.joblib" (
    echo [5/6] Training AI models...
    call .venv\Scripts\activate.bat
    python -m backend.app.ai.train
    call deactivate
) else (
    echo [5/6] AI models exist.
)

REM Start services
echo [6/6] Starting services...
echo.
echo Starting API server on http://localhost:8000
start "EcoMotorTwin API" cmd /c ".venv\Scripts\python.exe -m backend.app.main"

timeout /t 3 /nobreak >nul

echo Starting frontend on http://localhost:5173
start "EcoMotorTwin Frontend" cmd /c "cd frontend && npm.cmd run dev"

echo.
echo ============================================
echo  EcoMotorTwin is starting!
echo.
echo  API:      http://localhost:8000
echo  API Docs: http://localhost:8000/docs
echo  Frontend: http://localhost:5173
echo.
echo  Press Ctrl+C in each window to stop.
echo ============================================

REM Open browser
timeout /t 5 /nobreak >nul
start http://localhost:5173

endlocal
