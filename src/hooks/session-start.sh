#!/usr/bin/env bash
# functionmap-session-start.sh -- Detect mapped project from working directory

PYTHON=""
if command -v python3 &>/dev/null; then PYTHON="python3"
elif command -v python &>/dev/null; then PYTHON="python"
else exit 0; fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$PYTHON" "$SCRIPT_DIR/session-start.py"
