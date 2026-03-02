#!/bin/bash
set -euo pipefail

# Only run in remote (Claude Code on the web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR}"

echo "Installing Python dependencies..."
pip install --upgrade pip --quiet --break-system-packages 2>/dev/null || true
pip install -r requirements.txt --quiet --break-system-packages --ignore-installed

echo "Creating required directories..."
mkdir -p uploads outputs static

echo "Session setup complete."
