# Parish Newsletter

Automated monthly parish newsletter system. Group secretaries email their updates to a dedicated Gmail account. An LLM writes the text, a fixed HTML template sets the design. Distribution via Brevo.

## Architecture

- **Monthly pipeline** (`scripts/run_monthly.sh`): collect emails → check status → compose → Brevo draft campaign + test email to the admin.
- **Approval happens in Brevo**: the admin reviews the test email and sends the campaign from Brevo. No script sends to subscribers.
- **Corrections**: `scripts/compose.py --notes "…"` re-composes with the admin's instructions; `scripts/publish_brevo.py` then updates the same draft campaign and sends a new test.
- **Reminders** (`scripts/send_reminder.py`): emails secretaries who haven't submitted.

## Key files

- `scripts/common.py` — shared helpers (.env, config, IMAP/SMTP, submission status). New scripts import from it.
- `prompts/compose.md` — content prompt. The model returns JSON (`greeting`, `sections[{group_id, text}]`, `closing`) with light markup: blank-line paragraphs, `**bold**`, `*italics*`, `- ` lists. Never HTML.
- `prompts/style.md` — tone and language only.
- `prompts/template.html` — the only source of the visual design. The block between `<!-- SECTION` and `<!-- /SECTION -->` is repeated per group. `{{ unsubscribe }}` (with spaces) is Brevo's placeholder, filled at send time.
- `config.yaml` — parish data, groups (`id`, `name`, `emoji`, `secretary_email`), Brevo list and sender.
- `data/submissions/YYYY-MM/` — group markdown files collected from email.
- `data/drafts/` — `YYYY-MM-draft.html` and `YYYY-MM-brevo.json` (id of the month's Brevo campaign).
- `logs/` — monthly run logs. `data/token_log.jsonl` — token usage per compose.

## Model

`compose.py` calls `claude -p` with `--tools ""`: the submissions are outside text and may carry instructions. `compose.py` escapes everything the model returns before putting it in the template.

## Environment

- `.env`: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `ADMIN_EMAIL`, `BREVO_API_KEY`.
- Gmail is only used internally (IMAP to collect, SMTP for reminders).
- Not scheduled on this machine. Intended cron schedule:
  - Days 10-25: `collect_emails.py` daily at 08:00
  - Day 20: `send_reminder.py` at 09:00
  - Day 25: `run_monthly.sh` at 10:00
