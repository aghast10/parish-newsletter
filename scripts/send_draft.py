#!/usr/bin/env python3
"""Send the composed draft to the admin for review via email."""

import os
import smtplib
import sys
from datetime import date
from email.mime.text import MIMEText
from pathlib import Path

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
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))

today = date.today()
month_str = today.strftime("%Y-%m")

# Spanish month names
MONTH_NAMES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def main():
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print(f"[{today}] Email credentials not configured.")
        sys.exit(1)

    if not ADMIN_EMAIL:
        print(f"[{today}] ADMIN_EMAIL not configured.")
        sys.exit(1)

    draft_file = PROJECT_DIR / "data" / "drafts" / f"{month_str}-draft.html"
    if not draft_file.exists():
        print(f"[{today}] No draft found for {month_str}.")
        sys.exit(1)

    html_content = draft_file.read_text(encoding="utf-8")
    month_name = MONTH_NAMES.get(today.month, str(today.month))

    # Wrap the draft in instructions for the admin
    body = f"""<div style="font-family:sans-serif;max-width:640px;margin:auto;padding:16px;background:#f9f9f9;border:1px solid #ddd;margin-bottom:24px">
<p><strong>BORRADOR — Boletín Parroquial de {month_name.capitalize()} {today.year}</strong></p>
<p>Revise el boletín a continuación y responda a este correo con:</p>
<ul>
<li><strong>APROBAR</strong> — para publicar el boletín tal cual.</li>
<li><strong>CORREGIR:</strong> seguido de las instrucciones de corrección.</li>
</ul>
</div>
<hr style="margin:24px 0">
{html_content}"""

    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = f"BORRADOR Boletín Parroquial — {month_name.capitalize()} {today.year}"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ADMIN_EMAIL

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"[{today}] Draft sent to {ADMIN_EMAIL} for review.")
    except Exception as e:
        print(f"[{today}] Failed to send draft: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
