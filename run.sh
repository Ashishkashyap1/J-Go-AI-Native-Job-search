#!/bin/bash
# ============================================
# LITSEARCH - One-Click Launcher (Linux/Mac)
# ============================================
# Usage:
#   ./run.sh                          (uses default CV location)
#   ./run.sh /path/to/your_cv.pdf     (custom CV path)
# ============================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Find CV path ---
if [ -z "$1" ]; then
    CV_PATH="$HOME/Desktop/Ashish_CV.pdf"
    if [ ! -f "$CV_PATH" ]; then
        echo ""
        echo "[!] No CV found at default location: $CV_PATH"
        read -p "Enter path to your CV PDF: " CV_PATH
    fi
else
    CV_PATH="$1"
fi

# --- Check CV exists ---
if [ ! -f "$CV_PATH" ]; then
    echo "[ERROR] CV file not found: $CV_PATH"
    exit 1
fi

# --- Check Python ---
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found. Install from https://python.org"
    exit 1
fi

# --- Install deps if needed ---
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "[*] First run - installing dependencies..."
    python3 -m venv "$SCRIPT_DIR/.venv"
    source "$SCRIPT_DIR/.venv/bin/activate"
    pip install -r "$SCRIPT_DIR/requirements.txt" -q
    python -m playwright install chromium
else
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# --- Run LITSEARCH ---
echo ""
python -m LITSEARCH --cv "$CV_PATH" "$@"
