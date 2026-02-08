#!/bin/bash

# VidStega Demo Setup Script (Linux/Mac)

echo "========================================="
echo "VidStega Demo Setup"
echo "========================================="
echo ""

# Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.8+ from https://www.python.org/"
    exit 1
fi

echo "[1/6] Checking Python version..."
python3 --version

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo ""
    echo "[2/6] Creating virtual environment..."
    python3 -m venv venv
else
    echo ""
    echo "[2/6] Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "[3/6] Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "[4/6] Upgrading pip..."
python -m pip install --upgrade pip -q

# Install requirements
echo ""
echo "[5/6] Installing dependencies..."
echo "This may take a few minutes..."
pip install -r requirements.txt -q

if [ $? -ne 0 ]; then
    echo ""
    echo "WARNING: Some packages failed to install"
    echo "Trying to install core packages only..."
    pip install flask flask-socketio flask-cors celery redis opencv-python numpy reedsolo cryptography
fi

# Create required directories
echo ""
echo "[6/6] Creating directories..."
mkdir -p uploads outputs static stress_test_results

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Your VidStega demo environment is ready!"
echo ""
echo "To start the application:"
echo "  1. Run: ./run_demo.sh"
echo "  2. Open browser: http://localhost:5000"
echo ""
echo "Or manually:"
echo "  1. Activate environment: source venv/bin/activate"
echo "  2. Run server: python run.py"
echo ""
echo "For detailed instructions, see: DEMO_GUIDE.md"
echo ""
