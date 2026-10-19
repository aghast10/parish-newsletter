"""Shared helpers: .env, config, dates, IMAP/SMTP and submission status."""

import email
import hashlib
import imaplib
import os
import re
import smtplib
import sys
from datetime import date
from email.header import decode_header, make_header
from email.utils import parseaddr
from html.parser import HTMLParser
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
        # utf-8-sig: Windows Notepad may save .env with a BOM.
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
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


def message_key(msg):
    """Stable id for a message: its Message-ID, or a hash of a few headers."""
    mid = (msg.get("Message-ID") or "").strip()
    if mid:
        return mid
    raw = "|".join(str(msg.get(h, "")) for h in ("From", "Date", "Subject"))
    return "sha1:" + hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()


def is_auto_reply(msg):
    """Out-of-office replies, bounces and list mail, not real submissions."""
    auto = (msg.get("Auto-Submitted") or "").strip().lower()
    precedence = (msg.get("Precedence") or "").strip().lower()
    return ((auto and auto != "no")
            or precedence in ("auto_reply", "bulk", "junk", "list")
            or msg.get("X-Autoreply") is not None
            or msg.get("X-Autorespond") is not None
            or msg.get_content_type() == "multipart/report")


def _decode_part(part):
    payload = part.get_payload(decode=True) or b""
    try:
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _is_attachment(part):
    return "attachment" in (part.get("Content-Disposition") or "").lower()


class _HTMLText(HTMLParser):
    """Plain text from an email's HTML, leaving out quoted replies."""

    BLOCK = {"p", "div", "br", "tr", "table", "ul", "ol",
             "h1", "h2", "h3", "h4", "h5", "h6", "hr"}
    SKIP = {"style", "script", "head", "title", "blockquote"}
    QUOTE_CLASSES = {"gmail_quote", "gmail_attr", "yahoo_quoted", "moz-cite-prefix"}
    VOID = {"br", "hr", "img", "meta", "link", "input", "wbr", "col", "area", "base"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.stack = []      # True for each open element that hides its content
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        classes = set((dict(attrs).get("class") or "").split())
        if tag in self.BLOCK or tag == "li":
            self.out.append("\n")
        if tag == "li" and not self.hidden:
            self.out.append("- ")
        if tag in self.VOID:
            return
        hide = tag in self.SKIP or bool(classes & self.QUOTE_CLASSES)
        self.stack.append(hide)
        self.hidden += hide

    def handle_startendtag(self, tag, attrs):
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCK or tag == "li":
            self.out.append("\n")
        if tag in self.VOID or not self.stack:
            return
        self.hidden -= self.stack.pop()

    def handle_data(self, data):
        if not self.hidden:
            self.out.append(re.sub(r"[ \t\r\n]+", " ", data))


def html_to_text(html):
    parser = _HTMLText()
    parser.feed(html)
    parser.close()
    return "\n".join(line.strip() for line in "".join(parser.out).split("\n"))


def _clean_body(body):
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


def extract_body(msg) -> str:
    """Plain-text body of an email.Message, without quoted reply lines.

    Uses the text/plain part; if there is none or it is empty, the text/html
    part converted to plain text.
    """
    parts = [p for p in msg.walk() if not _is_attachment(p)]
    for ctype, convert in (("text/plain", None), ("text/html", html_to_text)):
        for part in parts:
            if part.get_content_type() != ctype:
                continue
            text = _decode_part(part)
            body = _clean_body(convert(text) if convert else text)
            if body:
                return body
    return ""


def header_text(value):
    """Readable text of an encoded header ('=?utf-8?q?...?=' → text), on one line."""
    try:
        text = str(make_header(decode_header(value or "")))
    except Exception:
        text = value or ""
    return " ".join(text.split())


def _decode_filename(name):
    return header_text(name)


def safe_filename(name):
    """A file name that can't leave its directory or hide as a dotfile."""
    name = re.split(r"[\\/]", name)[-1]
    name = re.sub(r"[^\w.\- ]+", "_", name).strip(" .")
    return name[:120] or "adjunto"


def extract_attachments(msg):
    """[(filename, content_type, bytes)] for every attached file.

    Counts parts marked as attachments and any non-text part with a file
    name (inline images). The text/plain and text/html body parts are not
    attachments.
    """
    found = []
    for part in msg.walk():
        if part.is_multipart() or part.get_content_type() == "message/rfc822":
            continue
        ctype = part.get_content_type()
        filename = part.get_filename()
        if not _is_attachment(part) and (not filename or ctype.startswith("text/")):
            continue
        name = _decode_filename(filename) if filename else f"adjunto-{len(found) + 1}"
        found.append((name, ctype, part.get_payload(decode=True) or b""))
    return found


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
    # BODY.PEEK[] leaves \Seen alone; collect_emails.py keeps its own state.
    status, data = mail.fetch(msg_id, "(BODY.PEEK[])")
    if status != "OK" or not data or not isinstance(data[0], tuple):
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
