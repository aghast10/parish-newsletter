#!/usr/bin/env python3
"""Show submission status: which groups have submitted and which haven't."""

import sys
from datetime import date

from common import load_config, submission_status, today


def print_status(month_str):
    """Print the status table and return how many groups have submitted."""
    groups = load_config().get("groups", [])
    status = submission_status(groups, month_str)

    print(f"\n  Boletín Parroquial — Estado de envíos ({month_str})")
    print("  " + "─" * 55)
    print(f"  {'Grupo':<25} {'Estado':<12} {'Palabras':>10}  {'Recibido'}")
    print("  " + "─" * 55)

    for group, path in status:
        if path:
            word_count = len(path.read_text(encoding="utf-8").split())
            mod_time = date.fromtimestamp(path.stat().st_mtime).isoformat()
            print(f"  {group['name']:<25} {'✓ Sí':<12} {word_count:>10}  {mod_time}")
        else:
            print(f"  {group['name']:<25} {'✗ No':<12} {'—':>10}  —")

    submitted = sum(1 for _, path in status if path)
    print("  " + "─" * 55)
    print(f"  Total: {submitted}/{len(groups)} grupos han enviado.\n")
    return submitted


if __name__ == "__main__":
    print_status(sys.argv[1] if len(sys.argv) > 1 else today.strftime("%Y-%m"))
