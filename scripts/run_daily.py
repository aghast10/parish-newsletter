#!/usr/bin/env python3
"""Daily entry point for the scheduler: does whatever the newsletter needs today.

The GitHub Actions workflow (.github/workflows/diario.yml) runs it twice a
day; on the Windows fallback (windows/instalar.bat), a daily task and the
Startup folder do (--wait gives the network time to come up at logon). Each
run looks at the date (`schedule` in config.yaml) and at what is already done
this month:

- from collection_start_day to the day before publish_day: collect emails;
- from reminder_day to the day before publish_day: send the reminder, once a
  month (recorded in data/run_daily.json);
- from publish_day to the end of the month: the monthly pipeline
  (run_monthly.py), until the month's Brevo campaign exists
  (data/drafts/YYYY-MM-brevo.json). A failed run is retried on the next one.

Running it several times a day is safe, and a missed run is caught up by the
next one within the month. A lock (data/run_daily.lock) skips a run that
starts while another is going on.
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime

from common import DRAFTS_DIR, PROJECT_DIR, load_config, today
from run_monthly import echo, run_pipeline, run_step, setup_console

STATE_FILE = PROJECT_DIR / "data" / "run_daily.json"
LOCK_FILE = PROJECT_DIR / "data" / "run_daily.lock"
STALE_LOCK_SECONDS = 3600


def acquire_lock():
    """False if another run holds the lock (one left by a crash expires in an hour)."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        if time.time() - LOCK_FILE.stat().st_mtime > STALE_LOCK_SECONDS:
            LOCK_FILE.unlink()
    except FileNotFoundError:
        pass
    try:
        os.close(os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL))
        return True
    except FileExistsError:
        return False


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def main():
    schedule = load_config().get("schedule", {})
    start_day = schedule.get("collection_start_day", 10)
    reminder_day = schedule.get("reminder_day", 20)
    publish_day = schedule.get("publish_day", 25)
    month = today.strftime("%Y-%m")

    echo(f"=== Daily run: {datetime.now():%Y-%m-%d %H:%M:%S} ===")

    if today.day >= publish_day:
        if (DRAFTS_DIR / f"{month}-brevo.json").exists():
            echo(f"The {month} draft is already in Brevo. Nothing to do.")
            return True
        return run_pipeline()

    if today.day < start_day:
        echo(f"Collection starts on day {start_day}. Nothing to do.")
        return True

    ok = run_step("Collect emails", "collect_emails.py")

    # After collecting, so a group that has just sent its update isn't reminded.
    state = load_state()
    if today.day >= reminder_day and state.get("reminder_sent") != month:
        if run_step("Reminders", "send_reminder.py"):
            state["reminder_sent"] = month
            save_state(state)
        else:
            ok = False
    return ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wait", type=int, default=0, metavar="SECONDS",
                        help="sleep this long before starting")
    args = parser.parse_args()
    setup_console()
    time.sleep(args.wait)
    if not acquire_lock():
        echo(f"=== Daily run: {datetime.now():%Y-%m-%d %H:%M:%S}: another run is going on, skipping ===")
        sys.exit(0)
    try:
        ok = main()
    except Exception:
        echo(traceback.format_exc())
        ok = False
    finally:
        LOCK_FILE.unlink(missing_ok=True)
    sys.exit(0 if ok else 1)
