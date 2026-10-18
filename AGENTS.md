# Parish Newsletter

Automated monthly parish newsletter system. Group secretaries email their updates to a dedicated Gmail account. An LLM writes the text, a fixed HTML template sets the design. Distribution via Brevo.

## Architecture

- **Monthly pipeline** (`scripts/run_monthly.sh`): collect emails → check status → compose → Brevo draft campaign + test email to the admin.
- **Approval happens in Brevo**: the admin reviews the test email and sends the campaign from Brevo. No script sends to subscribers.
- **Corrections**: `scripts/compose.py --notes "…"` re-composes with the admin's instructions; `scripts/publish_brevo.py` then updates the same draft campaign and sends a new test.
- **Reminders** (`scripts/send_reminder.py`): emails secretaries who haven't submitted.
- **Collection** (`scripts/collect_emails.py`): searches INBOX since the previous month's publish day and fetches with `BODY.PEEK[]`. The state is `data/submissions/processed.json` (Message-IDs already handled), not Gmail's read flag, so reading the inbox in Gmail loses nothing and re-running duplicates nothing. To re-collect a message, delete its entry there. Unknown senders are logged and not recorded (adding the address to `config.yaml` picks them up next run); auto-replies and empty emails are recorded and skipped. HTML-only emails are converted to text. Attachments are saved to `data/submissions/YYYY-MM/attachments/{group_id}/` and listed in the group's `.md` with a note to review them by hand (their content is not read). Each collected email gets a receipt to the secretary in Spanish (`--no-receipt` to skip, `--dry-run` writes and sends nothing).

## Key files

- `scripts/common.py` — shared helpers (.env, config, IMAP/SMTP, submission status). New scripts import from it.
- `prompts/compose.md` — content prompt. The model returns JSON (`greeting`, `sections[{group_id, text}]`, `closing`) with light markup: blank-line paragraphs, `**bold**`, `*italics*`, `- ` lists. Never HTML.
- `prompts/style.md` — tone and language only.
- `prompts/template.html` — the only source of the visual design. The block between `<!-- SECTION` and `<!-- /SECTION -->` is repeated per group. `{{ unsubscribe }}` (with spaces) is Brevo's placeholder, filled at send time.
- `config.yaml` — parish data, groups (`id`, `name`, `emoji`, `secretary_email`), Brevo list and sender.
- `data/submissions/YYYY-MM/` — group markdown files collected from email, plus `attachments/`.
- `data/submissions/processed.json` — Message-IDs `collect_emails.py` has already handled.
- `data/drafts/` — `YYYY-MM-draft.html` and `YYYY-MM-brevo.json` (id of the month's Brevo campaign).
- `logs/` — monthly run logs. `data/token_log.jsonl` — token usage per compose.

## Model

`scripts/llm.py` makes one API call that returns JSON matching a schema, through the Anthropic or the OpenAI SDK, depending on the `llm` section of `config.yaml` (`provider`, `model`, `effort` for Anthropic, `base_url` for OpenAI-compatible services). The output is constrained with structured outputs (`output_config.format` / `response_format: json_schema`), and `group_id` is an enum of the groups that submitted. No tools are passed. The submissions go in the user turn and the instructions in the system prompt: they are outside text and may carry instructions. `compose.py` escapes everything the model returns before putting it in the template. Anthropic calls use `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`), so a declined request is retried on a fallback model. Token usage goes to `data/token_log.jsonl`; the cost is computed only for the models in `log_tokens.PRICING`.

## Environment

- Python dependencies are in `requirements.txt`, installed in `.venv/` (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`). `run_monthly.sh` uses `.venv/bin/python` when it exists. Run the other scripts with `.venv/bin/python scripts/...`.
- `.env`: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `ADMIN_EMAIL`, `BREVO_API_KEY`, and `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`.
- Gmail is only used internally (IMAP to collect, SMTP for reminders and receipts).
- Not scheduled on this machine. Intended cron schedule:
  - Days 10-25: `collect_emails.py` daily at 08:00
  - Day 20: `send_reminder.py` at 09:00
  - Day 25: `run_monthly.sh` at 10:00
