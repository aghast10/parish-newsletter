#!/usr/bin/env python3
"""Collect group submissions via IMAP.

Matches sender addresses against config.yaml groups.
Saves plain-text body to data/submissions/YYYY-MM/{group_id}.md.
Multiple emails from the same group are appended with a separator.
"""

import imaplib
import email
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parent.parent

# Load .env
env_file = PROJECT_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

EMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", os.environ.get("EMAIL_ADDRESS", ""))
EMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", os.environ.get("EMAIL_PASSWORD", ""))

if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
    print("Email credentials not configured in .env")
    sys.exit(1)

IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))

today = date.today()
month_str = today.strftime("%Y-%m")


def load_config():
    config_file = PROJECT_DIR / "config.yaml"
    with config_file.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_email_address(from_header):
    """Extract bare email address from a From header."""
    match = re.search(r"<([^>]+)>", from_header)
    if match:
        return match.group(1).strip().lower()
    return from_header.strip().lower()


def extract_body(msg) -> str:
    """Return plain-text body of an email.Message, stripping quoted lines."""
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = part.get("Content-Disposition", "")
            if ct == "text/plain" and "attachment" not in cd:
                charset = part.get_content_charset() or "utf-8"
                try:
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                break
    else:
        if msg.get_content_type() == "text/plain":
            charset = msg.get_content_charset() or "utf-8"
            try:
                body = msg.get_payload(decode=True).decode(charset, errors="replace")
            except Exception:
                body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

    lines = body.splitlines()
    clean = []
    for line in lines:
        s = line.strip()
        if s.startswith(">"):
            continue
        if re.match(r"^[-_=]{5,}$", s):
            continue
        if re.match(r"^El .+escribi[oó]:", s, re.IGNORECASE):
            continue
        if re.match(r"^On .+wrote:$", s, re.IGNORECASE):
            continue
        clean.append(s)

    # Collapse consecutive blank lines
    result, prev_blank = [], False
    for line in clean:
        if line == "":
            if not prev_blank:
                result.append("")
            prev_blank = True
        else:
            result.append(line)
            prev_blank = False

    return "\n".join(result).strip()


def find_group_by_email(sender_email, groups):
    """Match sender email to a group config entry."""
    for group in groups:
        if group.get("secretary_email", "").lower() == sender_email:
            return group
    return None


def main():
    config = load_config()
    groups = config.get("groups", [])

    if not groups:
        print(f"[{today}] No groups configured in config.yaml")
        return

    # Build email -> group mapping
    email_to_group = {}
    for g in groups:
        addr = g.get("secretary_email", "").lower()
        if addr:
            email_to_group[addr] = g

    submissions_dir = PROJECT_DIR / "data" / "submissions" / month_str
    submissions_dir.mkdir(parents=True, exist_ok=True)

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    except Exception as e:
        print(f"[{today}] IMAP connection failed: {e}")
        sys.exit(1)

    try:
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    except imaplib.IMAP4.error as e:
        print(f"[{today}] IMAP login failed: {e}")
        sys.exit(1)

    try:
        mail.select("INBOX")

        # Fetch all unseen emails
        status, data = mail.search(None, "UNSEEN")
        if status != "OK":
            print(f"[{today}] IMAP search failed.")
            return

        ids = data[0].split()
        if not ids:
            print(f"[{today}] No new emails found.")
            return

        print(f"[{today}] Found {len(ids)} new email(s).")
        collected = 0
        skipped = 0

        for msg_id in ids:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            try:
                msg = email.message_from_bytes(msg_data[0][1])
            except Exception as e:
                print(f"[{today}] Could not parse message {msg_id}: {e}")
                continue

            sender = msg.get("From", "")
            sender_email = extract_email_address(sender)
            body = extract_body(msg)

            group = find_group_by_email(sender_email, groups)
            if group is None:
                print(f"[{today}] Unknown sender: {sender_email}, skipping.")
                mail.store(msg_id, "+FLAGS", "\\Seen")
                skipped += 1
                continue

            if not body:
                print(f"[{today}] Empty body from {sender_email} ({group['name']}), skipping.")
                mail.store(msg_id, "+FLAGS", "\\Seen")
                continue

            # Save submission
            group_file = submissions_dir / f"{group['id']}.md"
            msg_date = msg.get("Date", "")

            if group_file.exists():
                # Append with separator
                with group_file.open("a", encoding="utf-8") as f:
                    f.write(f"\n\n---\n\n*[Actualización recibida: {msg_date}]*\n\n{body}")
                print(f"[{today}] Appended update from {group['name']} ({sender_email})")
            else:
                with group_file.open("w", encoding="utf-8") as f:
                    f.write(f"*[Recibido: {msg_date}]*\n\n{body}")
                print(f"[{today}] New submission from {group['name']} ({sender_email})")

            mail.store(msg_id, "+FLAGS", "\\Seen")
            collected += 1

        print(f"[{today}] Collected {collected} submission(s), skipped {skipped} unknown sender(s).")

    finally:
        try:
            mail.logout()
        except Exception:
            pass


if __name__ == "__main__":
    main()
