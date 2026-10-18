#!/usr/bin/env bash
# Monthly newsletter pipeline orchestrator.
# collect → status → compose → Brevo draft campaign + test email to admin
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
MONTH=$(date +%Y-%m)

# Project venv (anthropic/openai SDKs), see requirements.txt
PY="$PROJECT_DIR/.venv/bin/python"
[ -x "$PY" ] || PY=python3

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$MONTH.log"

echo "=== Newsletter Run: $(date) ===" | tee -a "$LOG"

echo "--- Step 1: Collect emails ---" | tee -a "$LOG"
"$PY" "$SCRIPT_DIR/collect_emails.py" 2>&1 | tee -a "$LOG"

echo "--- Step 2: Status ---" | tee -a "$LOG"
"$PY" "$SCRIPT_DIR/status.py" 2>&1 | tee -a "$LOG"

echo "--- Step 3: Compose ---" | tee -a "$LOG"
"$PY" "$SCRIPT_DIR/compose.py" 2>&1 | tee -a "$LOG"

echo "--- Step 4: Brevo draft + test email ---" | tee -a "$LOG"
"$PY" "$SCRIPT_DIR/publish_brevo.py" 2>&1 | tee -a "$LOG"

echo "=== Newsletter Run Done: $(date) ===" | tee -a "$LOG"
