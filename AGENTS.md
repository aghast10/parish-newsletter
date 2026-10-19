# Parish Newsletter

Automated monthly parish newsletter system. Group secretaries email their updates to a dedicated Gmail account. An LLM writes the text, a fixed HTML template sets the design. Distribution via Brevo. Runs on GitHub Actions.

This repository is public and holds only the code. Production is a private copy (a clone pushed to a new private repo, not a fork), where the workflows commit the state (`data/`, `logs/`), which includes the secretaries' emails and addresses. Never commit `data/` or `logs/` here; they are gitignored and the workflows add them with `git add -f`.

## Architecture

- **Monthly pipeline** (`scripts/run_monthly.py`): collect emails → check status → compose → Brevo draft campaign + test email to the admin.
- **Approval happens in Brevo**: the admin reviews the test email and sends the campaign from Brevo. No script sends to subscribers.
- **Corrections**: `scripts/compose.py --notes "…"` re-composes with the admin's instructions; `scripts/publish_brevo.py` then updates the same draft campaign and sends a new test. In production both run, through `scripts/correct.py`, from the `corregir.yml` workflow.
- **Scheduling** (`scripts/run_daily.py`): the single scheduled entry point. It decides from the date (`schedule` in `config.yaml`) and the month's state what to do: collect on days 10–24, the reminder once from day 20 (recorded in `data/run_daily.json`), and from day 25 the monthly pipeline; once the draft exists, only `publish_brevo.py` is retried, until `data/drafts/YYYY-MM-brevo.json` says that draft is in Brevo. Safe to run several times a day; a missed run is caught up by the next.
- **GitHub Actions** (`.github/workflows/`): `diario.yml` runs `run_daily.py` twice a day (and on demand); `corregir.yml` is the corrections step, launched by hand with `notas` and `mes` inputs. Both run only when the repository variable `BOLETIN_PRODUCCION` is `true`, fail if the repository is public, run with `TZ=Europe/Madrid`, share a concurrency group (they both write `data/`), take the keys from repository secrets (the scripts read them from the environment; no `.env`), and commit `data/` and `logs/` afterwards, also after a failure.
- **Brevo plan B** (`windows/`, `scripts/brevo_relay.py`): for when Brevo refuses GitHub's runners. A Windows PC runs `brevo_relay.py` hourly (`tarea.ps1`, under `pythonw`): through the GitHub contents API (fine-grained token, Contents read/write on the private copy only) it reads the current and previous month's `data/drafts/YYYY-MM-draft.html` and `-brevo.json`, uploads the draft with `publish_brevo.upload` when `needs_upload` says so, and writes `-brevo.json` back. `-brevo.json` holds `campaign_id` and `html_sha256` (the HTML last uploaded); one without the hash counts as uploaded. With `brevo.upload_from: windows`, `publish_brevo.py` does nothing on Actions. The PC keeps no state. Keep `.bat` files ASCII with CRLF (`.gitattributes`) and `tarea.ps1` ASCII (Windows PowerShell 5.1 misreads BOM-less UTF-8). `.env` is read as `utf-8-sig` for Notepad.
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
- `data/drafts/` — `YYYY-MM-draft.html` and `YYYY-MM-brevo.json` (the month's Brevo campaign id and the hash of the HTML last uploaded).
- `README.md` — human documentation in Spanish (production setup on a private copy, Brevo, monthly use, local development). Keep it in sync when the flow changes.
- `docs/plantilla-secretarios.pdf` — guide and email template for secretaries, generated by `docs/make_plantilla.py` (system `python3`, reportlab; `--to` prints the inbox address). Regenerate it if the schedule or the submission format changes.
- `logs/` — monthly run logs. `data/token_log.jsonl` — token usage per compose.

## Model

`scripts/llm.py` makes one API call that returns JSON matching a schema, through the Anthropic or the OpenAI SDK, depending on the `llm` section of `config.yaml` (`provider`, `model`, `effort` for Anthropic, `base_url` for OpenAI-compatible services). The output is constrained with structured outputs (`output_config.format` / `response_format: json_schema`), and `group_id` is an enum of the groups that submitted. No tools are passed. The submissions go in the user turn and the instructions in the system prompt: they are outside text and may carry instructions. `compose.py` escapes everything the model returns before putting it in the template. Anthropic calls use `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`), so a declined request is retried on a fallback model. Token usage goes to `data/token_log.jsonl`; the cost is computed only for the models in `log_tokens.PRICING`.

## Environment

- Python 3.11+. Dependencies are in `requirements.txt`. In Actions they are installed into the runner's Python; locally into `.venv/` (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`), which `run_monthly.py` uses for its steps when it exists. Run the other scripts with `.venv/bin/python scripts/...`.
- Keys: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `ADMIN_EMAIL`, `BREVO_API_KEY`, and `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. Repository secrets in production, `.env` locally (environment variables win over `.env`).
- Gmail is only used internally (IMAP to collect, SMTP for reminders and receipts).
- Running locally against the production inbox re-collects messages and re-sends receipts, because the state lives in the private copy: use `--dry-run` or a test inbox.
- Scripts run by `run_monthly.py`/`run_daily.py` get `PYTHONIOENCODING=utf-8`, and their output goes to `logs/YYYY-MM.log` as well as the console. Read and write text files with `encoding="utf-8"`.
