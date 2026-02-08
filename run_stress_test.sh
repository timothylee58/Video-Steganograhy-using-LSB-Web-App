#!/bin/bash

# VidStega Stress Test Runner
# This script sets up the environment and runs comprehensive stress tests

echo "========================================"
echo "VidStega Stress Test Suite"
echo "========================================"
echo ""

# Check Python version
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "⚠ Virtual environment not found. Creating..."
    python -m venv venv
fi

# Activate virtual environment
echo "✓ Activating virtual environment..."
source venv/bin/activate || . venv/Scripts/activate

# Install/upgrade required packages
echo "✓ Installing dependencies..."
pip install -q --upgrade pip
pip install -q numpy opencv-python psutil reedsolo

# Check system resources
echo ""
echo "System Resources:"
echo "----------------"
python -c "
import psutil
print(f'  CPU Cores: {psutil.cpu_count()}')
print(f'  Total RAM: {psutil.virtual_memory().total / (1024**3):.1f} GB')
print(f'  Available RAM: {psutil.virtual_memory().available / (1024**3):.1f} GB')
print(f'  Disk Space: {psutil.disk_usage(\"/\").free / (1024**3):.1f} GB free')
"

# Create output directory
mkdir -p stress_test_results

echo ""
echo "========================================"
echo "Starting Stress Tests..."
echo "========================================"
echo ""
echo "This will test:"
echo "  ✓ 4 resolutions (480p, 720p, 1080p, 1440p)"
echo "  ✓ 3 encryption strengths (AES-128, 192, 256)"
echo "  ✓ 4 cipher modes (CBC, CTR, GCM, CFB)"
echo "  ✓ 5 video lengths (1s to 20s)"
echo ""
echo "Estimated time: 45-60 minutes"
echo "Results will be saved to: stress_test_results/"
echo ""

read -p "Press Enter to continue or Ctrl+C to cancel..."

# Run the stress test
python stress_test.py

echo ""
echo "========================================"
echo "Stress Test Complete!"
echo "========================================"
echo ""
echo "Results available at:"
echo "  - stress_test_results/stress_test_results.json"
echo "  - stress_test_results/analysis_report.md"
echo ""
echo "Review SCALABILITY_ANALYSIS.md for detailed recommendations."
echo ""
