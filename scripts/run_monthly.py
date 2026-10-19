#!/usr/bin/env python3
"""Monthly newsletter pipeline: collect → status → compose → Brevo draft campaign + test email.

Runs each step with the project venv's interpreter (or this one, as in GitHub
Actions) and stops at the first one that fails. Output goes to the screen and
to logs/YYYY-MM.log.
"""

import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = PROJECT_DIR / "scripts"
LOG_DIR = PROJECT_DIR / "logs"

STEPS = [
    ("Step 1: Collect emails", "collect_emails.py"),
    ("Step 2: Status", "status.py"),
    ("Step 3: Compose", "compose.py"),
    ("Step 4: Brevo draft + test email", "publish_brevo.py"),
]


def venv_python():
    """The project venv's python (see requirements.txt), else this interpreter."""
    path = PROJECT_DIR / ".venv" / "bin" / "python"
    return str(path) if path.exists() else sys.executable


def echo(text):
    """A line to the screen and to logs/YYYY-MM.log."""
    LOG_DIR.mkdir(exist_ok=True)
    with (LOG_DIR / f"{date.today():%Y-%m}.log").open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text, flush=True)


def run_step(title, script, *args):
    """Run scripts/<script>, logging its output. True if it exited with 0."""
    echo(f"--- {title} ---")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [venv_python(), str(SCRIPT_DIR / script), *args],
        cwd=PROJECT_DIR, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace",
    )
    for line in proc.stdout:
        echo(line.rstrip("\n"))
    code = proc.wait()
    if code:
        echo(f"!!! {script} failed (exit code {code})")
    return code == 0


def run_pipeline():
    echo(f"=== Newsletter Run: {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    for title, script in STEPS:
        if not run_step(title, script):
            echo(f"=== Newsletter Run FAILED: {datetime.now():%Y-%m-%d %H:%M:%S} ===")
            return False
    echo(f"=== Newsletter Run Done: {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_pipeline() else 1)
