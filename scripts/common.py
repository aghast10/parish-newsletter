"""Shared helpers: .env, config, dates, IMAP/SMTP and submission status."""

import email
import imaplib
import os
import re
import smtplib
import sys
from datetime import date
from email.utils import parseaddr
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parent.parent
SUBMISSIONS_ROOT = PROJECT_DIR / "data" / "submissions"
DRAFTS_DIR = PROJECT_DIR / "data" / "drafts"

MONTH_NAMES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def load_env():
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


load_env()

EMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", os.environ.get("EMAIL_ADDRESS", ""))
EMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", os.environ.get("EMAIL_PASSWORD", ""))
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

today = date.today()


def load_config():
    with (PROJECT_DIR / "config.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def month_label(month_str):
    """'2026-10' -> ('octubre', 2026)."""
    year, month = (int(x) for x in month_str.split("-"))
    return MONTH_NAMES[month], year


def log(text):
    print(f"[{today}] {text}")


def fail(text):
    log(text)
    sys.exit(1)


# ── Submissions ─────────────────────────────────────────────────────

def submission_status(groups, month_str):
    """[(group, Path or None)] in config order."""
    month_dir = SUBMISSIONS_ROOT / month_str
    result = []
    for group in groups:
        path = month_dir / f"{group['id']}.md"
        result.append((group, path if path.exists() else None))
    return result


# ── Email ───────────────────────────────────────────────────────────

def require_email_credentials():
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        fail("Email credentials not configured in .env")


def sender_address(msg):
    return parseaddr(msg.get("From", ""))[1].strip().lower()


def extract_body(msg) -> str:
    """Plain-text body of an email.Message, without quoted reply lines."""
    part = next(
        (p for p in msg.walk()
         if p.get_content_type() == "text/plain"
         and "attachment" not in p.get("Content-Disposition", "")),
        None,
    )
    if part is None:
        return ""
    payload = part.get_payload(decode=True) or b""
    try:
        body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    except LookupError:
        body = payload.decode("utf-8", errors="replace")

    clean, prev_blank = [], False
    for line in body.splitlines():
        s = line.strip()
        if (s.startswith(">")
                or re.match(r"^[-_=]{5,}$", s)
                or re.match(r"^El .+escribi[oó]:", s, re.IGNORECASE)
                or re.match(r"^On .+wrote:$", s, re.IGNORECASE)):
            continue
        if s == "" and prev_blank:
            continue
        prev_blank = s == ""
        clean.append(s)
    return "\n".join(clean).strip()


def imap_connect():
    host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    port = int(os.environ.get("IMAP_PORT", "993"))
    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    except (OSError, imaplib.IMAP4.error) as e:
        fail(f"IMAP connection/login failed: {e}")
    return mail


def fetch_message(mail, msg_id):
    status, data = mail.fetch(msg_id, "(RFC822)")
    if status != "OK":
        return None
    try:
        return email.message_from_bytes(data[0][1])
    except Exception as e:
        log(f"Could not parse message {msg_id}: {e}")
        return None


def smtp_connect():
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    server = smtplib.SMTP_SSL(host, port)
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    return server
