#!/usr/bin/env python3
"""Publish the approved newsletter to Mautic and trigger send."""

import os
import sys
from datetime import date
from pathlib import Path

import requests
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
    config = load_config()
    mautic_config = config.get("mautic", {})

    base_url = os.environ.get("MAUTIC_BASE_URL", mautic_config.get("base_url", ""))
    username = os.environ.get("MAUTIC_USERNAME", "")
    password = os.environ.get("MAUTIC_PASSWORD", "")
    segment_id = mautic_config.get("segment_id", 1)

    if not base_url or not username or not password:
        print(f"[{today}] Mautic credentials not configured.")
        sys.exit(1)

    published_file = PROJECT_DIR / "data" / "published" / f"{month_str}-final.html"
    if not published_file.exists():
        print(f"[{today}] No published newsletter found for {month_str}.")
        sys.exit(1)

    html_content = published_file.read_text(encoding="utf-8")
    month_name = MONTH_NAMES.get(today.month, str(today.month))
    parish_name = config.get("parish", {}).get("name", "Parroquia")

    api_url = base_url.rstrip("/") + "/api"
    auth = (username, password)

    # Step 1: Create email in Mautic
    email_data = {
        "name": f"Boletín Parroquial — {month_name} {today.year}",
        "subject": f"Boletín Parroquial — {month_name.capitalize()} {today.year}",
        "customHtml": html_content,
        "emailType": "list",
        "lists": [segment_id],
        "isPublished": True,
    }

    print(f"[{today}] Creating email in Mautic...")
    resp = requests.post(
        f"{api_url}/emails/new",
        json=email_data,
        auth=auth,
        headers={"Content-Type": "application/json"},
    )

    if resp.status_code not in (200, 201):
        print(f"[{today}] Mautic email creation failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    email_id = resp.json().get("email", {}).get("id")
    if not email_id:
        print(f"[{today}] Could not get email ID from Mautic response.")
        sys.exit(1)

    print(f"[{today}] Email created in Mautic (ID: {email_id})")

    # Step 2: Send the email to the segment
    print(f"[{today}] Triggering send to segment {segment_id}...")
    send_resp = requests.post(
        f"{api_url}/emails/{email_id}/send",
        auth=auth,
    )

    if send_resp.status_code not in (200, 201):
        print(f"[{today}] Mautic send failed: {send_resp.status_code} {send_resp.text}")
        sys.exit(1)

    print(f"[{today}] Newsletter sent via Mautic successfully!")


if __name__ == "__main__":
    main()
