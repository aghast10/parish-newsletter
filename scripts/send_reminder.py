#!/usr/bin/env python3
"""Send reminder emails to secretaries who haven't submitted yet."""

import os
import smtplib
import sys
from datetime import date
from email.mime.text import MIMEText
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


def load_config():
    config_file = PROJECT_DIR / "config.yaml"
    with config_file.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print(f"[{today}] Gmail credentials not configured.")
        sys.exit(1)

    config = load_config()
    groups = config.get("groups", [])
    parish_name = config.get("parish", {}).get("name", "la Parroquia")
    schedule = config.get("schedule", {})
    publish_day = schedule.get("publish_day", 25)

    submissions_dir = PROJECT_DIR / "data" / "submissions" / month_str
    month_name = MONTH_NAMES.get(today.month, str(today.month))

    missing = []
    for group in groups:
        group_file = submissions_dir / f"{group['id']}.md"
        if not group_file.exists():
            missing.append(group)

    if not missing:
        print(f"[{today}] All groups have submitted. No reminders needed.")
        return

    print(f"[{today}] Sending reminders to {len(missing)} group(s)...")

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)

            for group in missing:
                recipient = group.get("secretary_email", "")
                if not recipient:
                    continue

                body = f"""Estimado/a responsable de {group['name']},

Este es un recordatorio amistoso de que aún no hemos recibido la información de {group['name']} para el boletín parroquial de {month_name}.

Por favor, envíe su contribución respondiendo a este correo o escribiendo a {EMAIL_ADDRESS} antes del día {publish_day}.

Puede incluir:
- Actividades realizadas durante el mes
- Próximos eventos o fechas importantes
- Cualquier información que quiera compartir con la comunidad

Muchas gracias por su colaboración.

Un saludo,
{parish_name}
"""

                msg = MIMEText(body, "plain", "utf-8")
                msg["Subject"] = f"Recordatorio: Boletín parroquial de {month_name}"
                msg["From"] = EMAIL_ADDRESS
                msg["To"] = recipient

                server.send_message(msg)
                print(f"[{today}] Reminder sent to {group['name']} <{recipient}>")

    except Exception as e:
        print(f"[{today}] Failed to send reminders: {e}")
        sys.exit(1)

    print(f"[{today}] {len(missing)} reminder(s) sent.")


if __name__ == "__main__":
    main()
