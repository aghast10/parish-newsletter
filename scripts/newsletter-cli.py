#!/usr/bin/env python3
"""Parish Newsletter CLI — manage groups, check status, and run pipeline."""

import os
import subprocess
import sys
from datetime import date

import yaml

from common import PROJECT_DIR, load_config
from status import print_status

CONFIG_FILE = PROJECT_DIR / "config.yaml"

# ── Colors ──────────────────────────────────────────────────────────

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"

if os.name == "nt":
    os.system("")  # turns on ANSI colors in the Windows console


# ── Config helpers ──────────────────────────────────────────────────

def save_config(config):
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ── Display helpers ─────────────────────────────────────────────────

def prompt(text="  > "):
    try:
        return input(text).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"


def status_dot(active):
    return f"{GREEN}●{NC}" if active else f"{RED}○{NC}"


# ── Screens ─────────────────────────────────────────────────────────

def screen_status():
    print_status(date.today().strftime("%Y-%m"))
    prompt("  [Enter] back ")


def screen_groups():
    while True:
        config = load_config()
        groups = config.get("groups", [])

        print()
        print(f"  {BOLD}Groups{NC}")
        print("  " + "─" * 50)
        for i, g in enumerate(groups, 1):
            print(f"  {i}) {g['name']:<25} <{g.get('secretary_email', '')}>"
                  f"  {DIM}({g['id']}){NC}")
        if not groups:
            print(f"  {DIM}(none configured){NC}")
        print("  " + "─" * 50)
        print(f"  {BOLD}Actions:{NC} [a] add  [d] delete  [b] back")
        choice = prompt()
        if choice == "a":
            add_group(config)
        elif choice == "d":
            delete_group(config, groups)
        elif choice in ("b", "q", ""):
            break


def add_group(config):
    print()
    print(f"  {BOLD}Add group{NC}")
    name = prompt("  Group name: ")
    if not name:
        return

    group_id = prompt(f"  ID [{name.lower().replace(' ', '_')}]: ")
    if not group_id:
        group_id = name.lower().replace(" ", "_")

    email_addr = prompt("  Secretary email: ")
    if not email_addr or "@" not in email_addr:
        print(f"  {RED}Invalid email.{NC}")
        return

    emoji = prompt("  Emoji for the section header (optional): ")
    description = prompt("  Description (optional): ")

    group = {
        "id": group_id,
        "name": name,
        "emoji": emoji or "✦",
        "secretary_email": email_addr,
        "description": description or "",
    }

    if "groups" not in config:
        config["groups"] = []
    config["groups"].append(group)
    save_config(config)
    print(f"  {GREEN}✓{NC} Added {name}")


def delete_group(config, groups):
    if not groups:
        print(f"  {RED}No groups to delete.{NC}")
        return
    print()
    print(f"  {BOLD}Delete group:{NC}")
    for i, g in enumerate(groups, 1):
        print(f"  {i}) {g['name']}")
    choice = prompt()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(groups):
            group = groups[idx]
            confirm = prompt(f"  Remove {group['name']}? [y/N] ")
            if confirm.lower() == "y":
                config["groups"].pop(idx)
                save_config(config)
                print(f"  {RED}✗{NC} Removed {group['name']}")
    except (ValueError, IndexError):
        pass


def screen_run():
    print()
    print(f"  {BOLD}Run Pipeline{NC}")
    print("  " + "─" * 40)
    print("  1) Collect emails")
    print("  2) Compose newsletter")
    print("  3) Send reminders")
    print("  4) Upload draft to Brevo + test email")
    print("  5) Full pipeline (collect → compose → Brevo draft)")
    print("  " + "─" * 40)
    choice = prompt()

    script_dir = PROJECT_DIR / "scripts"
    if choice == "1":
        subprocess.run([sys.executable, str(script_dir / "collect_emails.py")])
    elif choice == "2":
        subprocess.run([sys.executable, str(script_dir / "compose.py")])
    elif choice == "3":
        subprocess.run([sys.executable, str(script_dir / "send_reminder.py")])
    elif choice == "4":
        subprocess.run([sys.executable, str(script_dir / "publish_brevo.py")])
    elif choice == "5":
        subprocess.run([sys.executable, str(script_dir / "run_monthly.py")])


def screen_brevo():
    brevo = load_config().get("brevo", {})
    not_set = DIM + "not set" + NC

    print()
    print(f"  {BOLD}Brevo Configuration{NC}")
    print("  " + "─" * 40)
    print(f"  List ID:     {brevo.get('list_id', not_set)}")
    print(f"  Sender:      {brevo.get('sender_name', not_set)} <{brevo.get('sender_email', '')}>")
    print("  " + "─" * 40)
    print(f"  {DIM}Edit config.yaml and .env (BREVO_API_KEY) to change Brevo settings.{NC}")
    print()
    prompt("  [Enter] back ")


def main_menu():
    while True:
        print()
        print(f"  {BOLD}Parish Newsletter CLI{NC}")
        print("  ═════════════════════════════════")
        print("  1) Submission status")
        print("  2) Groups")
        print("  3) Run pipeline")
        print("  4) Brevo config")
        print("  ═════════════════════════════════")
        print(f"  {DIM}[q] quit{NC}")
        choice = prompt()
        if choice == "1":
            screen_status()
        elif choice == "2":
            screen_groups()
        elif choice == "3":
            screen_run()
        elif choice == "4":
            screen_brevo()
        elif choice in ("q", "Q", ""):
            break
        else:
            print(f"  {RED}Invalid option.{NC}")


if __name__ == "__main__":
    main_menu()
