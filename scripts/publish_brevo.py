#!/usr/bin/env python3
"""Upload the month's draft to Brevo as a draft campaign and send a test to the admin.

Usage: publish_brevo.py [--month YYYY-MM] [--dry-run]

Nothing goes to the subscribers from here: the admin reviews the test email and
sends the campaign from Brevo (Campaigns → the draft → Send). Running it again
after a re-compose updates the same campaign and sends a new test.

data/drafts/YYYY-MM-brevo.json keeps the campaign id and the hash of the HTML
last uploaded, so a draft that changed (or never made it) shows as pending.
With `brevo.upload_from: windows` in config.yaml it does nothing on GitHub
Actions: windows/ uploads the draft from a PC (brevo_relay.py).
"""

import argparse
import hashlib
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


def html_hash(html):
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def needs_upload(html, state):
    """True if this draft isn't the one in Brevo yet.

    State files from before the hash was kept only have campaign_id: those
    count as uploaded.
    """
    if "campaign_id" not in state:
        return True
    return state.get("html_sha256", html_hash(html)) != html_hash(html)


def campaign_payload(month, html, brevo_cfg):
    month_name, year = month_label(month)
    title = f"Boletín Parroquial — {month_name.capitalize()} {year}"
    return {
        "name": title,
        "subject": title,
        "sender": {"name": brevo_cfg.get("sender_name", ""), "email": brevo_cfg.get("sender_email", "")},
        "htmlContent": html,
        "recipients": {"listIds": [brevo_cfg.get("list_id", 1)]},
    }


def upload(month, html, brevo_cfg, state, save, api_key, admin_email):
    """Create or update the month's campaign and send the test.

    save(state) is called as soon as the campaign exists (so a retry updates
    it instead of creating another) and again once the test has gone out.
    """
    campaign = campaign_payload(month, html, brevo_cfg)
    state = dict(state)
    if "campaign_id" in state:
        campaign_id = state["campaign_id"]
        # Brevo only lets drafts and scheduled campaigns be edited, so this also
        # refuses to touch a campaign that has already gone out.
        brevo("PUT", f"/emailCampaigns/{campaign_id}", api_key, campaign)
        log(f"Updated Brevo draft campaign {campaign_id}.")
    else:
        campaign_id = brevo("POST", "/emailCampaigns", api_key, campaign)["id"]
        state["campaign_id"] = campaign_id
        save(state)
        log(f"Created Brevo draft campaign {campaign_id}.")

    brevo("POST", f"/emailCampaigns/{campaign_id}/sendTest", api_key, {"emailTo": [admin_email]})
    state["html_sha256"] = html_hash(html)
    save(state)
    log(f"Test email sent to {admin_email}. Send the campaign from Brevo once it looks right.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--month", default=today.strftime("%Y-%m"))
    parser.add_argument("--dry-run", action="store_true", help="print the request, call nothing")
    args = parser.parse_args()

    brevo_cfg = load_config().get("brevo", {})
    if brevo_cfg.get("upload_from") == "windows" and os.environ.get("GITHUB_ACTIONS") == "true":
        log("brevo.upload_from is 'windows': the PC uploads the draft to Brevo (windows/).")
        return

    api_key = os.environ.get("BREVO_API_KEY", "")
    if not args.dry_run and not (api_key and ADMIN_EMAIL):
        fail("BREVO_API_KEY and ADMIN_EMAIL must be set in .env")

    draft_file = DRAFTS_DIR / f"{args.month}-draft.html"
    if not draft_file.exists():
        fail(f"No draft found for {args.month}. Run compose.py first.")
    html = draft_file.read_text(encoding="utf-8")

    if args.dry_run:
        campaign = campaign_payload(args.month, html, brevo_cfg)
        shown = {**campaign, "htmlContent": f"<{len(html)} chars>"}
        print(json.dumps(shown, ensure_ascii=False, indent=2))
        print(f"Test email would go to: {ADMIN_EMAIL or '(ADMIN_EMAIL not set)'}")
        return

    state_file = DRAFTS_DIR / f"{args.month}-brevo.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    upload(args.month, html, brevo_cfg, state,
           lambda s: state_file.write_text(json.dumps(s), encoding="utf-8"),
           api_key, ADMIN_EMAIL)


if __name__ == "__main__":
    main()
