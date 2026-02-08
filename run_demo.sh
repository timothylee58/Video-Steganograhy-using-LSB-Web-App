#!/bin/bash

# VidStega Demo Runner (Linux/Mac)

echo "========================================="
echo "Starting VidStega Demo"
echo "========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "ERROR: Virtual environment not found!"
    echo "Please run setup_demo.sh first"
    exit 1
fi

# Activate virtual environment
echo "[1/3] Activating virtual environment..."
source venv/bin/activate

# Check if Flask app exists
if [ ! -f "run.py" ]; then
    echo "ERROR: run.py not found!"
    echo "Make sure you're in the project root directory"
    exit 1
fi

# Set environment variables for demo
echo ""
echo "[2/3] Setting up demo environment..."
export FLASK_ENV=development
export FLASK_DEBUG=1

# Create required directories
mkdir -p uploads outputs static

# Check for Redis (optional)
echo ""
echo "[3/3] Starting Flask server..."
echo ""
echo "NOTE: Running in synchronous mode (no Celery/Redis required)"
echo "This is perfect for demos and single-user showcasing."
echo ""
echo "========================================="
echo "Server Starting..."
echo "========================================="
echo ""
echo "Access the application at:"
echo "  http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop the server"
echo "========================================="
echo ""

# Start Flask app
python run.py
