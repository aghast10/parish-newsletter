#!/usr/bin/env python3
"""Show submission status: which groups have submitted and which haven't."""

import os
import sys
from datetime import date
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parent.parent

today = date.today()
month_str = sys.argv[1] if len(sys.argv) > 1 else today.strftime("%Y-%m")


def load_config():
    config_file = PROJECT_DIR / "config.yaml"
    with config_file.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    config = load_config()
    groups = config.get("groups", [])
    submissions_dir = PROJECT_DIR / "data" / "submissions" / month_str

    print(f"\n  Boletín Parroquial — Estado de envíos ({month_str})")
    print("  " + "─" * 55)
    print(f"  {'Grupo':<25} {'Estado':<12} {'Palabras':>10}  {'Recibido'}")
    print("  " + "─" * 55)

    submitted_count = 0

    for group in groups:
        group_file = submissions_dir / f"{group['id']}.md"
        if group_file.exists():
            content = group_file.read_text(encoding="utf-8")
            word_count = len(content.split())
            mod_time = date.fromtimestamp(group_file.stat().st_mtime).isoformat()
            status = "✓ Sí"
            print(f"  {group['name']:<25} {status:<12} {word_count:>10}  {mod_time}")
            submitted_count += 1
        else:
            status = "✗ No"
            print(f"  {group['name']:<25} {status:<12} {'—':>10}  —")

    print("  " + "─" * 55)
    print(f"  Total: {submitted_count}/{len(groups)} grupos han enviado.\n")

    return submitted_count


if __name__ == "__main__":
    main()
