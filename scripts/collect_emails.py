#!/usr/bin/env python3
"""Collect group submissions via IMAP.

Matches sender addresses against config.yaml groups.
Saves plain-text body to data/submissions/YYYY-MM/{group_id}.md.
Multiple emails from the same group are appended with a separator.
"""

from common import (
    SUBMISSIONS_ROOT, extract_body, fetch_message, imap_connect, load_config, log,
    require_email_credentials, sender_address, today,
)


def main():
    require_email_credentials()
    groups = load_config().get("groups", [])
    if not groups:
        log("No groups configured in config.yaml")
        return

    email_to_group = {
        g["secretary_email"].lower(): g for g in groups if g.get("secretary_email")
    }

    submissions_dir = SUBMISSIONS_ROOT / today.strftime("%Y-%m")
    submissions_dir.mkdir(parents=True, exist_ok=True)

    mail = imap_connect()
    try:
        mail.select("INBOX")

        status, data = mail.search(None, "UNSEEN")
        if status != "OK":
            log("IMAP search failed.")
            return

        ids = data[0].split()
        if not ids:
            log("No new emails found.")
            return

        log(f"Found {len(ids)} new email(s).")
        collected = skipped = 0

        for msg_id in ids:
            msg = fetch_message(mail, msg_id)
            if msg is None:
                continue

            sender_email = sender_address(msg)
            group = email_to_group.get(sender_email)
            if group is None:
                log(f"Unknown sender: {sender_email}, skipping.")
                mail.store(msg_id, "+FLAGS", "\\Seen")
                skipped += 1
                continue

            body = extract_body(msg)
            if not body:
                log(f"Empty body from {sender_email} ({group['name']}), skipping.")
                mail.store(msg_id, "+FLAGS", "\\Seen")
                continue

            group_file = submissions_dir / f"{group['id']}.md"
            msg_date = msg.get("Date", "")

            if group_file.exists():
                with group_file.open("a", encoding="utf-8") as f:
                    f.write(f"\n\n---\n\n*[Actualización recibida: {msg_date}]*\n\n{body}")
                log(f"Appended update from {group['name']} ({sender_email})")
            else:
                group_file.write_text(f"*[Recibido: {msg_date}]*\n\n{body}", encoding="utf-8")
                log(f"New submission from {group['name']} ({sender_email})")
            mail.store(msg_id, "+FLAGS", "\\Seen")
            collected += 1

        log(f"Collected {collected} submission(s), skipped {skipped} unknown sender(s).")

    finally:
        try:
            mail.logout()
        except Exception:
            pass


if __name__ == "__main__":
    main()
