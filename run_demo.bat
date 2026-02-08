@echo off
REM VidStega Demo Runner (Windows)

echo =========================================
echo Starting VidStega Demo
echo =========================================
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo ERROR: Virtual environment not found!
    echo Please run setup_demo.bat first
    pause
    exit /b 1
)

REM Activate virtual environment
echo [1/3] Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if Flask app exists
if not exist "run.py" (
    echo ERROR: run.py not found!
    echo Make sure you're in the project root directory
    pause
    exit /b 1
)

REM Set environment variables for demo
echo.
echo [2/3] Setting up demo environment...
set FLASK_ENV=development
set FLASK_DEBUG=1

REM Create required directories
if not exist "uploads" mkdir uploads
if not exist "outputs" mkdir outputs
if not exist "static" mkdir static

REM Check for Redis (optional)
echo.
echo [3/3] Starting Flask server...
echo.
echo NOTE: Running in synchronous mode (no Celery/Redis required)
echo This is perfect for demos and single-user showcasing.
echo.
echo =========================================
echo Server Starting...
echo =========================================
echo.
echo Access the application at:
echo   http://localhost:5000
echo.
echo Press Ctrl+C to stop the server
echo =========================================
echo.

REM Start Flask app
python run.py

pause
