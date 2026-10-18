#!/usr/bin/env python3
"""Collect group submissions via IMAP.

Matches sender addresses against config.yaml groups.
Saves the text body to data/submissions/YYYY-MM/{group_id}.md (the text/html
part converted to text when there is no plain-text part). Multiple emails from
the same group are appended with a separator. Attached files are saved under
data/submissions/YYYY-MM/attachments/{group_id}/ and listed in the .md file.

State lives in data/submissions/processed.json (Message-IDs already handled),
not in Gmail's read/unread flag: messages are fetched with BODY.PEEK, and
someone reading the inbox in Gmail doesn't make submissions disappear. The
search covers everything since the previous month's publish day.

Each collected message gets a short receipt email to the secretary
(--no-receipt to skip). --dry-run writes and sends nothing.
"""

import argparse
import json
import os
from datetime import date, datetime
from email.mime.text import MIMEText

from common import (
    EMAIL_ADDRESS, MONTH_NAMES, SUBMISSIONS_ROOT, extract_attachments, extract_body,
    fetch_message, header_text, imap_connect, is_auto_reply, load_config, log, message_key,
    require_email_credentials, safe_filename, sender_address, smtp_connect, today,
)

PROCESSED_FILE = SUBMISSIONS_ROOT / "processed.json"
IMAP_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ── State ───────────────────────────────────────────────────────────

def load_processed(path=PROCESSED_FILE):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        # Starting from scratch would collect every message twice.
        raise SystemExit(f"Cannot read {path}: {e}. Fix or remove it by hand.")


def save_processed(processed, path=PROCESSED_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(processed, ensure_ascii=False, indent=1, sort_keys=True),
                   encoding="utf-8")
    os.replace(tmp, path)


def search_since(publish_day, ref=None):
    """IMAP SINCE date: the previous month's publish day (inclusive).

    Everything that arrived after the last newsletter was composed belongs to
    this one; processed.json skips what was already collected on that day.
    """
    ref = ref or today
    year, month = (ref.year, ref.month - 1) if ref.month > 1 else (ref.year - 1, 12)
    d = date(year, month, min(int(publish_day), 28))
    return f"{d.day:02d}-{IMAP_MONTHS[d.month - 1]}-{d.year}"


# ── Processing one message ──────────────────────────────────────────

def save_attachments(attachments, target_dir):
    """Write files into target_dir without overwriting. [(name, ctype, size)]."""
    target_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for name, ctype, data in attachments:
        base = safe_filename(name)
        stem, dot, ext = base.rpartition(".")
        if not dot:
            stem, ext = base, ""
        path, n = target_dir / base, 2
        while path.exists():
            path = target_dir / (f"{stem}-{n}.{ext}" if ext else f"{stem}-{n}")
            n += 1
        path.write_bytes(data)
        saved.append((path.name, ctype, len(data)))
    return saved


def attachment_note(files, rel_dir):
    listed = ", ".join(f"{name} ({ctype}, {max(1, round(size / 1024))} KB)"
                       for name, ctype, size in files)
    return (f"*[Adjuntos no incluidos en el texto, revisar a mano: {listed}. "
            f"Guardados en {rel_dir}/]*")


def process_message(msg, email_to_group, submissions_dir, dry_run=False):
    """Save one message's submission. Returns (status, group, info).

    status: "unknown" (sender not in config, not recorded as processed),
    "auto-reply", "empty", "collected".
    info: {"attachments": [names], "has_body": bool}.
    """
    sender = sender_address(msg)
    group = email_to_group.get(sender)
    if group is None:
        return "unknown", None, {}
    if is_auto_reply(msg):
        return "auto-reply", group, {}

    body = extract_body(msg)
    attachments = extract_attachments(msg)
    if not body and not attachments:
        return "empty", group, {}

    rel_dir = f"attachments/{group['id']}"
    files = []
    if attachments:
        if dry_run:
            files = [(safe_filename(n), c, len(d)) for n, c, d in attachments]
        else:
            files = save_attachments(attachments, submissions_dir / rel_dir)

    parts = [body] if body else []
    if files:
        parts.append(attachment_note(files, rel_dir))
    content = "\n\n".join(parts)

    group_file = submissions_dir / f"{group['id']}.md"
    msg_date = msg.get("Date", "")
    # The subject can carry information (a date, an event name) that the body leaves out.
    subject = header_text(msg.get("Subject"))
    header = f"\n*[Asunto: {subject}]*" if subject else ""
    if not dry_run:
        if group_file.exists():
            with group_file.open("a", encoding="utf-8") as f:
                f.write(f"\n\n---\n\n*[Actualización recibida: {msg_date}]*{header}\n\n{content}")
        else:
            group_file.write_text(f"*[Recibido: {msg_date}]*{header}\n\n{content}", encoding="utf-8")
    return "collected", group, {"attachments": [f[0] for f in files], "has_body": bool(body)}


# ── Receipt ─────────────────────────────────────────────────────────

def receipt_message(msg, group, info, parish_name, month_name, publish_day):
    extra = ""
    if info["attachments"] and info["has_body"]:
        extra = (f"\nTambién hemos recibido {len(info['attachments'])} archivo(s) adjunto(s). "
                 "El boletín se redacta a partir del texto del correo, así que si el adjunto "
                 "tiene información que quiera publicar, le agradeceríamos que la copiara "
                 "también en el cuerpo del mensaje.\n")
    elif info["attachments"]:
        extra = ("\nEl correo solo traía archivos adjuntos, sin texto. El boletín se redacta "
                 "a partir del texto del correo, así que le agradeceríamos que nos enviara "
                 "la información escrita en el cuerpo del mensaje.\n")

    body = f"""Estimado/a responsable de {group['name']},

Hemos recibido su contribución para el boletín parroquial de {month_name}. Muchas gracias.
{extra}
Si quiere añadir o corregir algo, puede responder a este correo antes del día {publish_day}.

Un saludo,
{parish_name}
"""
    reply = MIMEText(body, "plain", "utf-8")
    subject = (msg.get("Subject") or "").strip()
    reply["Subject"] = (subject if subject.lower().startswith("re:") else f"Re: {subject}") \
        if subject else f"Recibido: boletín parroquial de {month_name}"
    reply["From"] = EMAIL_ADDRESS
    reply["To"] = group["secretary_email"]
    reply["Auto-Submitted"] = "auto-replied"
    mid = (msg.get("Message-ID") or "").strip()
    if mid:
        reply["In-Reply-To"] = mid
        reply["References"] = f"{(msg.get('References') or '').strip()} {mid}".strip()
    return reply


def send_receipts(receipts):
    if not receipts:
        return
    try:
        with smtp_connect() as server:
            for reply in receipts:
                try:
                    server.send_message(reply)
                    log(f"Receipt sent to {reply['To']}")
                except Exception as e:
                    log(f"WARNING: receipt to {reply['To']} failed: {e}")
    except Exception as e:
        log(f"WARNING: could not send receipts: {e}")


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be collected; write and send nothing")
    parser.add_argument("--no-receipt", action="store_true",
                        help="Don't email secretaries a receipt")
    args = parser.parse_args()

    require_email_credentials()
    config = load_config()
    groups = config.get("groups", [])
    if not groups:
        log("No groups configured in config.yaml")
        return
    parish_name = config.get("parish", {}).get("name", "la Parroquia")
    publish_day = config.get("schedule", {}).get("publish_day", 25)

    email_to_group = {
        g["secretary_email"].lower(): g for g in groups if g.get("secretary_email")
    }

    month_str = today.strftime("%Y-%m")
    submissions_dir = SUBMISSIONS_ROOT / month_str
    if not args.dry_run:
        submissions_dir.mkdir(parents=True, exist_ok=True)
    processed = load_processed()
    since = search_since(publish_day)

    mail = imap_connect()
    receipts = []
    try:
        mail.select("INBOX", readonly=args.dry_run)

        status, data = mail.search(None, "SINCE", since)
        if status != "OK":
            log("IMAP search failed.")
            return

        ids = data[0].split()
        log(f"{len(ids)} email(s) in INBOX since {since}.")
        collected = unknown = new = 0

        for msg_id in ids:
            msg = fetch_message(mail, msg_id)
            if msg is None:
                continue
            key = message_key(msg)
            if key in processed:
                continue
            new += 1

            sender = sender_address(msg)
            outcome, group, info = process_message(
                msg, email_to_group, submissions_dir, dry_run=args.dry_run)

            if outcome == "unknown":
                # Not recorded: if the address is added to config.yaml later,
                # the next run picks the message up.
                log(f"Unknown sender: {sender} ({msg.get('Subject', '')!r}), skipping.")
                unknown += 1
                continue
            if outcome == "auto-reply":
                log(f"Auto-reply from {sender} ({group['name']}), ignoring.")
            elif outcome == "empty":
                log(f"WARNING: empty email from {sender} ({group['name']}), nothing saved.")
            else:
                collected += 1
                log(f"Submission from {group['name']} ({sender})")
                verb = "would save" if args.dry_run else "saved"
                for name in info["attachments"]:
                    log(f"  attachment {verb}: {month_str}/attachments/{group['id']}/{name}")
                if info["attachments"] and not info["has_body"]:
                    log(f"WARNING: {group['name']} sent only attachments; "
                        "the text has to be added by hand.")
                if not args.no_receipt:
                    receipts.append(receipt_message(
                        msg, group, info, parish_name, MONTH_NAMES[today.month], publish_day))

            if not args.dry_run:
                processed[key] = {
                    "status": outcome,
                    "group": group["id"],
                    "month": month_str,
                    "from": sender,
                    "processed_at": datetime.now().isoformat(timespec="seconds"),
                }
                save_processed(processed)
                # Only a visual hint in Gmail; processed.json is the state.
                mail.store(msg_id, "+FLAGS", "\\Seen")

        log(f"{new} new email(s): collected {collected}, "
            f"skipped {unknown} from unknown senders.")

    finally:
        try:
            mail.logout()
        except Exception:
            pass

    if args.dry_run:
        if receipts:
            log(f"Dry run: {len(receipts)} receipt(s) not sent.")
        return
    send_receipts(receipts)


if __name__ == "__main__":
    main()
