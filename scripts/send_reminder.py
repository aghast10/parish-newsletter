#!/usr/bin/env python3
"""Send reminder emails to secretaries who haven't submitted yet."""

from email.mime.text import MIMEText

from common import (
    EMAIL_ADDRESS, MONTH_NAMES, fail, load_config, log, require_email_credentials,
    smtp_connect, submission_status, today,
)


def main():
    require_email_credentials()

    config = load_config()
    parish_name = config.get("parish", {}).get("name", "la Parroquia")
    publish_day = config.get("schedule", {}).get("publish_day", 25)
    month_name = MONTH_NAMES[today.month]

    missing = [
        g for g, path in submission_status(config.get("groups", []), today.strftime("%Y-%m"))
        if path is None and g.get("secretary_email")
    ]
    if not missing:
        log("All groups have submitted. No reminders needed.")
        return

    log(f"Sending reminders to {len(missing)} group(s)...")

    try:
        with smtp_connect() as server:
            for group in missing:
                recipient = group["secretary_email"]
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
                log(f"Reminder sent to {group['name']} <{recipient}>")

    except Exception as e:
        fail(f"Failed to send reminders: {e}")

    log(f"{len(missing)} reminder(s) sent.")


if __name__ == "__main__":
    main()
