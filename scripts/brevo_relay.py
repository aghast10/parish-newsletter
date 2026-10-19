#!/usr/bin/env python3
"""Upload to Brevo, from this computer, the drafts GitHub Actions couldn't upload.

Usage: brevo_relay.py [--wait SECONDS]

For when Brevo refuses GitHub's servers. GitHub Actions still collects and
composes; this reads the private repository through the GitHub API and, for
this month and the previous one, uploads the draft if it isn't the one in
Brevo yet (data/drafts/YYYY-MM-brevo.json, see publish_brevo.py). Then it
writes that file back to the repository, so GitHub sees the draft as done.

windows/instalar.bat schedules it (hourly, and at logon with --wait so the
network is up). Needs in .env: GITHUB_REPO (owner/name), GITHUB_TOKEN (a
fine-grained token with Contents read and write on that repository only),
BREVO_API_KEY and ADMIN_EMAIL. Output goes to logs/brevo-relay.log.
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import date

import requests
import yaml

from common import ADMIN_EMAIL, PROJECT_DIR, fail, log
from publish_brevo import needs_upload, upload

API_URL = "https://api.github.com"
LOG_FILE = PROJECT_DIR / "logs" / "brevo-relay.log"


class GitHubFile:
    """A file in the repository, read and written through the contents API."""

    def __init__(self, repo, token, path):
        self.url = f"{API_URL}/repos/{repo}/contents/{path}"
        self.path = path
        self.headers = {"authorization": f"Bearer {token}",
                        "accept": "application/vnd.github+json",
                        "x-github-api-version": "2022-11-28"}
        self.sha = None

    def read(self):
        """The file's text, or None if it doesn't exist."""
        resp = requests.get(self.url, headers=self.headers, timeout=30)
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            fail(f"GitHub GET {self.path} failed: {resp.status_code} {resp.text}")
        data = resp.json()
        self.sha = data["sha"]
        return base64.b64decode(data["content"]).decode("utf-8")

    def write(self, text, message):
        payload = {"message": message, "content": base64.b64encode(text.encode("utf-8")).decode()}
        if self.sha:
            payload["sha"] = self.sha
        resp = requests.put(self.url, headers=self.headers, json=payload, timeout=30)
        if resp.status_code >= 400:
            fail(f"GitHub PUT {self.path} failed: {resp.status_code} {resp.text}")
        self.sha = resp.json()["content"]["sha"]


class Tee:
    """Writes to the console (if there is one; not under pythonw) and the log."""

    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, text):
        for s in self.streams:
            s.write(text)

    def flush(self):
        for s in self.streams:
            s.flush()


def months_to_check(ref=None):
    ref = ref or date.today()
    previous = date(ref.year - (ref.month == 1), (ref.month - 2) % 12 + 1, 1)
    return [ref.strftime("%Y-%m"), previous.strftime("%Y-%m")]


def relay(repo, token, api_key):
    config = None
    for month in months_to_check():
        html = GitHubFile(repo, token, f"data/drafts/{month}-draft.html").read()
        if html is None:
            continue
        state_file = GitHubFile(repo, token, f"data/drafts/{month}-brevo.json")
        text = state_file.read()
        state = json.loads(text) if text else {}
        if not needs_upload(html, state):
            log(f"{month}: the draft is already in Brevo.")
            continue
        if config is None:
            config = yaml.safe_load(GitHubFile(repo, token, "config.yaml").read())
        log(f"{month}: uploading the draft to Brevo from this computer...")
        upload(month, html, config.get("brevo", {}), state,
               lambda s: state_file.write(json.dumps(s), f"Brevo {month}: subido desde Windows"),
               api_key, ADMIN_EMAIL)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wait", type=int, default=0, metavar="SECONDS",
                        help="sleep this long before starting")
    args = parser.parse_args()

    LOG_FILE.parent.mkdir(exist_ok=True)
    log_stream = LOG_FILE.open("a", encoding="utf-8", buffering=1)
    if sys.stdout is not None:
        sys.stdout.reconfigure(errors="replace")  # a Windows console's code page
    sys.stdout = Tee(sys.stdout, log_stream)
    sys.stderr = Tee(sys.stderr, log_stream)

    time.sleep(args.wait)
    repo, token = os.environ.get("GITHUB_REPO", ""), os.environ.get("GITHUB_TOKEN", "")
    api_key = os.environ.get("BREVO_API_KEY", "")
    if not (repo and token and api_key and ADMIN_EMAIL):
        fail("GITHUB_REPO, GITHUB_TOKEN, BREVO_API_KEY and ADMIN_EMAIL must be set in .env")
    try:
        relay(repo, token, api_key)
    except requests.RequestException as e:
        fail(f"Network error: {e}")


if __name__ == "__main__":
    main()
