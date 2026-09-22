# Parish Newsletter

Automated monthly parish newsletter system. Group secretaries email their updates to a dedicated Gmail account. Claude composes a unified HTML newsletter. Distribution via Mautic.

## Architecture

- **Monthly pipeline** (`scripts/run_monthly.sh`): collect emails → check status → compose (Sonnet) → email draft to admin → admin approval → publish via Mautic.
- **Reminders** (`scripts/send_reminder.py`): emails secretaries who haven't submitted.
- **Approval** (`scripts/check_approval.py`): polls IMAP for admin reply (APROBAR/CORREGIR).

## Key directories

- `prompts/` — Prompt templates. `compose.md` for Sonnet synthesis, `style.md` living style guide.
- `data/submissions/YYYY-MM/` — Group markdown files collected from email.
- `data/drafts/` — AI-generated HTML drafts.
- `data/published/` — Final sent newsletters.
- `scripts/` — All pipeline scripts.
- `logs/` — Monthly run logs.

## Models used

- **Claude Sonnet**: Composes the newsletter from group submissions + style guide → HTML.

## Pipeline flow

```
collect_emails.py → status.py → compose.sh → email draft to admin
                                                     ↓
                              admin replies APROBAR ← check_approval.py (cron, hourly)
                                                     ↓
                                              publish_mautic.py
```

## Environment

- `.env` contains `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `ADMIN_EMAIL`, Mautic credentials.
- Runs on a Raspberry Pi via cron.

## Cron schedule

- Days 10-25: collect emails daily at 08:00
- Day 20: send reminders at 09:00
- Day 25: compose + review at 10:00
- Days 25-27: check approval hourly
