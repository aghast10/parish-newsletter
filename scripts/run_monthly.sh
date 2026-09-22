#!/usr/bin/env bash
# Monthly newsletter pipeline orchestrator.
# collect → status → compose → send draft to admin for approval
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
TODAY=$(date +%Y-%m-%d)
MONTH=$(date +%Y-%m)

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$MONTH.log"

echo "=== Newsletter Run: $(date) ===" | tee -a "$LOG"

echo "--- Step 1: Collect emails ---" | tee -a "$LOG"
python3 "$SCRIPT_DIR/collect_emails.py" 2>&1 | tee -a "$LOG"

echo "--- Step 2: Status ---" | tee -a "$LOG"
python3 "$SCRIPT_DIR/status.py" 2>&1 | tee -a "$LOG"

echo "--- Step 3: Compose ---" | tee -a "$LOG"
bash "$SCRIPT_DIR/compose.sh" 2>&1 | tee -a "$LOG"

echo "--- Step 4: Send draft for review ---" | tee -a "$LOG"
python3 "$SCRIPT_DIR/send_draft.py" 2>&1 | tee -a "$LOG"

echo "=== Newsletter Run Done: $(date) ===" | tee -a "$LOG"
