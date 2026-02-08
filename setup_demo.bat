@echo off
REM VidStega Demo Setup Script (Windows)

echo =========================================
echo VidStega Demo Setup
echo =========================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/6] Checking Python version...
python --version

REM Check if virtual environment exists
if not exist "venv" (
    echo.
    echo [2/6] Creating virtual environment...
    python -m venv venv
) else (
    echo.
    echo [2/6] Virtual environment already exists
)

REM Activate virtual environment
echo.
echo [3/6] Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo.
echo [4/6] Upgrading pip...
python -m pip install --upgrade pip -q

REM Install requirements
echo.
echo [5/6] Installing dependencies...
echo This may take a few minutes...
pip install -r requirements.txt -q

if errorlevel 1 (
    echo.
    echo WARNING: Some packages failed to install
    echo Trying to install core packages only...
    pip install flask flask-socketio flask-cors celery redis opencv-python numpy reedsolo cryptography
)

REM Create required directories
echo.
echo [6/6] Creating directories...
if not exist "uploads" mkdir uploads
if not exist "outputs" mkdir outputs
if not exist "static" mkdir static
if not exist "stress_test_results" mkdir stress_test_results

echo.
echo =========================================
echo Setup Complete!
echo =========================================
echo.
echo Your VidStega demo environment is ready!
echo.
echo To start the application:
echo   1. Run: run_demo.bat
echo   2. Open browser: http://localhost:5000
echo.
echo Or manually:
echo   1. Activate environment: venv\Scripts\activate.bat
echo   2. Run server: python run.py
echo.
echo For detailed instructions, see: DEMO_GUIDE.md
echo.

pause
