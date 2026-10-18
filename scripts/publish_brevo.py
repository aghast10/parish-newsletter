#!/usr/bin/env python3
"""Upload the month's draft to Brevo as a draft campaign and send a test to the admin.

Usage: publish_brevo.py [--month YYYY-MM] [--dry-run]

Nothing goes to the subscribers from here: the admin reviews the test email and
sends the campaign from Brevo (Campaigns → the draft → Send). Running it again
after a re-compose updates the same campaign and sends a new test.
"""

import argparse
import json
import os

import requests

from common import ADMIN_EMAIL, DRAFTS_DIR, fail, load_config, log, month_label, today

API_URL = "https://api.brevo.com/v3"


def brevo(method, path, api_key, payload=None):
    resp = requests.request(
        method, f"{API_URL}{path}", json=payload, timeout=30,
        headers={"api-key": api_key, "accept": "application/json"},
    )
    if resp.status_code >= 400:
        fail(f"Brevo {method} {path} failed: {resp.status_code} {resp.text}")
    return resp.json() if resp.content else {}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--month", default=today.strftime("%Y-%m"))
    parser.add_argument("--dry-run", action="store_true", help="print the request, call nothing")
    args = parser.parse_args()

    brevo_cfg = load_config().get("brevo", {})
    api_key = os.environ.get("BREVO_API_KEY", "")
    if not args.dry_run and not (api_key and ADMIN_EMAIL):
        fail("BREVO_API_KEY and ADMIN_EMAIL must be set in .env")

    draft_file = DRAFTS_DIR / f"{args.month}-draft.html"
    if not draft_file.exists():
        fail(f"No draft found for {args.month}. Run compose.py first.")
    state_file = DRAFTS_DIR / f"{args.month}-brevo.json"

    month_name, year = month_label(args.month)
    title = f"Boletín Parroquial — {month_name.capitalize()} {year}"
    campaign = {
        "name": title,
        "subject": title,
        "sender": {"name": brevo_cfg.get("sender_name", ""), "email": brevo_cfg.get("sender_email", "")},
        "htmlContent": draft_file.read_text(encoding="utf-8"),
        "recipients": {"listIds": [brevo_cfg.get("list_id", 1)]},
    }

    if args.dry_run:
        shown = {**campaign, "htmlContent": f"<{len(campaign['htmlContent'])} chars>"}
        print(json.dumps(shown, ensure_ascii=False, indent=2))
        print(f"Test email would go to: {ADMIN_EMAIL or '(ADMIN_EMAIL not set)'}")
        return

    if state_file.exists():
        campaign_id = json.loads(state_file.read_text())["campaign_id"]
        # Brevo only lets drafts and scheduled campaigns be edited, so this also
        # refuses to touch a campaign that has already gone out.
        brevo("PUT", f"/emailCampaigns/{campaign_id}", api_key, campaign)
        log(f"Updated Brevo draft campaign {campaign_id}.")
    else:
        campaign_id = brevo("POST", "/emailCampaigns", api_key, campaign)["id"]
        state_file.write_text(json.dumps({"campaign_id": campaign_id}))
        log(f"Created Brevo draft campaign {campaign_id}.")

    brevo("POST", f"/emailCampaigns/{campaign_id}/sendTest", api_key, {"emailTo": [ADMIN_EMAIL]})
    log(f"Test email sent to {ADMIN_EMAIL}. Send the campaign from Brevo once it looks right.")


if __name__ == "__main__":
    main()
