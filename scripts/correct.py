#!/usr/bin/env python3
"""Re-compose the newsletter with the admin's notes and update the Brevo draft.

Usage: correct.py [--notes "…"] [--month YYYY-MM]

Asks for the notes when --notes is not given (windows/corregir.bat). Runs
compose.py --notes and publish_brevo.py, logging to logs/YYYY-MM.log. GitHub
Actions does the same in .github/workflows/corregir.yml.
"""

import argparse
import sys

from run_monthly import echo, run_step, setup_console


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--notes")
    parser.add_argument("--month")
    args = parser.parse_args()
    setup_console()

    notes = args.notes
    if notes is None:
        print("¿Qué hay que cambiar? Por ejemplo: Quita la fecha del retiro, aún no está confirmada.")
        notes = input("(Intro sin escribir nada: redactar de nuevo sin indicaciones)\n> ").strip()
    month = ["--month", args.month] if args.month else []

    echo(f"=== Corrección. Notas: {notes} ===")
    ok = (run_step("Compose", "compose.py", *month, "--notes", notes)
          and run_step("Brevo draft + test email", "publish_brevo.py", *month))
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
