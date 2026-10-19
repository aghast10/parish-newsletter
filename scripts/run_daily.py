#!/usr/bin/env python3
"""Daily entry point for the scheduler: does whatever the newsletter needs today.

The GitHub Actions workflow (.github/workflows/diario.yml) runs it twice a
day. Each run looks at the date (`schedule` in config.yaml) and at what is
already done this month:

- from collection_start_day to the day before publish_day: collect emails;
- from reminder_day to the day before publish_day: send the reminder, once a
  month (recorded in data/run_daily.json);
- from publish_day to the end of the month: the monthly pipeline
  (run_monthly.py). Once the draft is composed, only the Brevo upload is
  retried, until the draft in Brevo is that one (data/drafts/YYYY-MM-brevo.json,
  which windows/ also updates when it uploads instead of GitHub).

Running it several times a day is safe, and a missed run is caught up by the
next one within the month.
"""

import json
import sys
import traceback
from datetime import datetime

from common import DRAFTS_DIR, PROJECT_DIR, load_config, today
from publish_brevo import needs_upload
from run_monthly import echo, run_pipeline, run_step

STATE_FILE = PROJECT_DIR / "data" / "run_daily.json"


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
        draft = DRAFTS_DIR / f"{month}-draft.html"
        if not draft.exists():
            return run_pipeline()
        state_file = DRAFTS_DIR / f"{month}-brevo.json"
        state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
        if not needs_upload(draft.read_text(encoding="utf-8"), state):
            echo(f"The {month} draft is already in Brevo. Nothing to do.")
            return True
        # Composed but not in Brevo yet: upload it, don't compose it again.
        return run_step("Brevo draft + test email", "publish_brevo.py")

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
    try:
        ok = main()
    except Exception:
        echo(traceback.format_exc())
        ok = False
    sys.exit(0 if ok else 1)
