#!/usr/bin/env python3
"""Poll IMAP for admin approval of the newsletter draft.

Looks for replies to the draft email containing:
- "APROBAR" → triggers publish
- "CORREGIR: {instructions}" → re-compose with corrections (future)
- No reply after 48h → send reminder to admin
"""

import imaplib
import email
import os
import re
import subprocess
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
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))

today = date.today()
month_str = today.strftime("%Y-%m")

SUBJECT_FILTER = "BORRADOR Boletín Parroquial"


def load_config():
    config_file = PROJECT_DIR / "config.yaml"
    with config_file.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_email_address(from_header):
    match = re.search(r"<([^>]+)>", from_header)
    if match:
        return match.group(1).strip().lower()
    return from_header.strip().lower()


def extract_body(msg) -> str:
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

    # Strip quoted lines
    lines = body.splitlines()
    clean = []
    for line in lines:
        s = line.strip()
        if s.startswith(">"):
            continue
        if re.match(r"^El .+escribi[oó]:", s, re.IGNORECASE):
            continue
        if re.match(r"^On .+wrote:$", s, re.IGNORECASE):
            continue
        clean.append(s)
    return "\n".join(clean).strip()


def main():
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print(f"[{today}] Email credentials not configured.")
        sys.exit(1)

    if not ADMIN_EMAIL:
        print(f"[{today}] ADMIN_EMAIL not configured.")
        sys.exit(1)

    draft_file = PROJECT_DIR / "data" / "drafts" / f"{month_str}-draft.html"
    published_file = PROJECT_DIR / "data" / "published" / f"{month_str}-final.html"

    if published_file.exists():
        print(f"[{today}] Newsletter already published for {month_str}.")
        return

    if not draft_file.exists():
        print(f"[{today}] No draft found for {month_str}.")
        return

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    except Exception as e:
        print(f"[{today}] IMAP connection/login failed: {e}")
        sys.exit(1)

    try:
        mail.select("INBOX")

        status, data = mail.search(None, f'(UNSEEN SUBJECT "{SUBJECT_FILTER}")')
        if status != "OK":
            print(f"[{today}] IMAP search failed.")
            return

        ids = data[0].split()
        if not ids:
            print(f"[{today}] No approval emails found.")
            return

        for msg_id in ids:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            try:
                msg = email.message_from_bytes(msg_data[0][1])
            except Exception:
                continue

            sender = extract_email_address(msg.get("From", ""))
            if sender != ADMIN_EMAIL.lower():
                print(f"[{today}] Ignoring reply from non-admin: {sender}")
                mail.store(msg_id, "+FLAGS", "\\Seen")
                continue

            body = extract_body(msg)
            mail.store(msg_id, "+FLAGS", "\\Seen")

            if re.search(r"\bAPROBAR\b", body, re.IGNORECASE):
                print(f"[{today}] Admin approved the newsletter!")

                # Copy draft to published
                published_file.parent.mkdir(parents=True, exist_ok=True)
                published_file.write_text(draft_file.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"[{today}] Draft copied to {published_file}")

                # Trigger Mautic publish
                try:
                    subprocess.run(
                        ["python3", str(PROJECT_DIR / "scripts" / "publish_mautic.py")],
                        check=True,
                    )
                except subprocess.CalledProcessError as e:
                    print(f"[{today}] Mautic publish failed: {e}")
                return

            elif re.search(r"\bCORREGIR\b", body, re.IGNORECASE):
                # Extract correction instructions
                correction = re.sub(r"^.*?CORREGIR[:\s]*", "", body, flags=re.IGNORECASE).strip()
                print(f"[{today}] Admin requested corrections: {correction}")

                # Save corrections for re-compose
                corrections_file = PROJECT_DIR / "data" / "drafts" / f"{month_str}-corrections.txt"
                corrections_file.write_text(correction, encoding="utf-8")
                print(f"[{today}] Corrections saved. Re-run compose.sh to apply.")
                return

        print(f"[{today}] No actionable approval found.")

    finally:
        try:
            mail.logout()
        except Exception:
            pass


if __name__ == "__main__":
    main()
