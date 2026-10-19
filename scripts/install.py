#!/usr/bin/env python3
"""Interactive installer: asks for the keys and the schedule, then sets everything up.

On Windows, double-click instalar.bat; elsewhere, `python3 scripts/install.py`.
It asks for the Gmail, Brevo and Claude/OpenAI keys (and checks them), the
admin address and the schedule, then writes .env and config.yaml, creates
.venv with requirements.txt, registers the scheduled task (Windows Task
Scheduler via install_windows_task.ps1, or cron) and can regenerate the
secretaries' guide. Running it again offers the current values as defaults.

Standard library only: it runs before the venv exists. config.yaml is edited
line by line so its comments survive.
"""

import getpass
import imaplib
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"
CONFIG_FILE = PROJECT_DIR / "config.yaml"
VENV_DIR = PROJECT_DIR / ".venv"
WINDOWS = os.name == "nt"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if WINDOWS else "bin/python")
CRON_MARK = "# parish-newsletter (install.py)"

ANTHROPIC_MODELS = [
    ("claude-opus-5-5", "Claude Opus 5.5: la mejor redacción (unos céntimos al mes)"),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5: más barato"),
]


# ── Questions ───────────────────────────────────────────────────────

def ask(question, default="", check=None):
    shown = f" [{default}]" if default != "" else ""
    while True:
        answer = input(f"  {question}{shown}: ").strip() or str(default)
        error = "Hace falta un valor." if not answer else check(answer) if check else None
        if not error:
            return answer
        print(f"    {error}")


def mask(secret):
    return f"{secret[:4]}…{secret[-4:]}" if len(secret) > 12 else "…"


def ask_secret(question, current=""):
    hint = f" [Intro: mantener {mask(current)}]" if current else ""
    while True:
        answer = getpass.getpass(f"  {question} (no se ve al escribir){hint}: ").strip() or current
        if answer:
            if answer != current:
                print(f"    Recibida: {mask(answer)}")
            return answer
        print("    Hace falta un valor.")


def ask_yes(question, default=True):
    suffix = " [S/n]" if default else " [s/N]"
    while True:
        answer = input(f"  {question}{suffix}: ").strip().lower()
        if not answer:
            return default
        if answer in ("s", "si", "sí", "y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def ask_choice(question, options, default=None):
    """options: [(value, label)]. Returns the chosen value."""
    print(f"  {question}")
    for i, (value, label) in enumerate(options, 1):
        print(f"    {i}) {label}")
    values = [value for value, _ in options]
    default_n = values.index(default) + 1 if default in values else 1
    n = ask("Número", default_n,
            lambda a: None if a.isdigit() and 1 <= int(a) <= len(options) else "Elige un número de la lista.")
    return values[int(n) - 1]


def check_email(value):
    return None if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) else "No parece una dirección de correo."


def check_day(low, high):
    def check(value):
        ok = value.isdigit() and low <= int(value) <= high
        return None if ok else f"Tiene que ser un día entre {low} y {high}."
    return check


def check_time(value):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", value)
    return None if m and int(m[1]) < 24 and int(m[2]) < 60 else "Escribe la hora como HH:MM, por ejemplo 10:00."


def checked(asker, checker):
    """Ask, check, and offer to ask again while the check says it's wrong."""
    while True:
        value = asker()
        ok, message = checker(value)
        print(f"    {'✓' if ok else '!'} {message}")
        if ok is not False or not ask_yes("¿Volver a escribirla?"):
            return value


# ── Checks (True: valid, False: rejected, None: couldn't tell) ─────

def http_get(url, headers):
    request = urllib.request.Request(url, headers={"accept": "application/json", **headers})
    with urllib.request.urlopen(request, timeout=20) as resp:
        return json.load(resp)


def http_check(url, headers, what):
    try:
        return True, f"{what}: clave válida.", http_get(url, headers)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, f"{what} rechaza la clave ({e.code}).", None
        return None, f"No se pudo comprobar la clave de {what} ({e.code}).", None
    except (OSError, ValueError) as e:
        return None, f"No se pudo comprobar la clave de {what} ({e}).", None


def check_gmail(creds, env):
    address, password = creds
    try:
        mail = imaplib.IMAP4_SSL(env.get("IMAP_HOST", "imap.gmail.com"), int(env.get("IMAP_PORT", "993")))
    except OSError as e:
        return None, f"No se pudo conectar con el servidor de correo ({e})."
    try:
        mail.login(address, password)
        mail.logout()
        return True, "Gmail: acceso correcto."
    except imaplib.IMAP4.error:
        return False, ("Gmail rechaza la dirección o la contraseña. Tiene que ser una contraseña "
                       "de aplicación (https://myaccount.google.com/apppasswords).")


def check_llm(provider, key):
    if provider == "anthropic":
        url, headers = "https://api.anthropic.com/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"}
    else:
        url, headers = "https://api.openai.com/v1/models", {"authorization": f"Bearer {key}"}
    ok, message, _ = http_check(url, headers, "Anthropic" if provider == "anthropic" else "OpenAI")
    return ok, message


# ── .env ────────────────────────────────────────────────────────────

def is_placeholder(value):
    return not value or "example.com" in value or "..." in value or "xxxx" in value


def read_env():
    values = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values.setdefault(key.strip(), value.strip())
    return {k: v for k, v in values.items() if not is_placeholder(v)}


def write_env(updates):
    """Set keys in .env (made from .env.example the first time), keeping the rest."""
    base = ENV_FILE if ENV_FILE.exists() else PROJECT_DIR / ".env.example"
    lines = base.read_text(encoding="utf-8-sig").splitlines()
    pending = dict(updates)
    # Active lines first, then commented-out ones ("# OPENAI_API_KEY=...").
    for pattern in (r"([A-Z_]+)\s*=", r"#\s*([A-Z_]+)\s*="):
        for i, line in enumerate(lines):
            m = re.match(pattern, line.strip())
            if m and m[1] in pending:
                lines[i] = f"{m[1]}={pending.pop(m[1])}"
    lines += [f"{k}={v}" for k, v in pending.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── config.yaml (line edits, comments kept) ─────────────────────────

def _section(lines, section):
    """(header index, end index) of a top-level section."""
    start = next(i for i, l in enumerate(lines) if re.match(rf"{section}:\s*(#.*)?$", l))
    end = start + 1
    while end < len(lines) and not re.match(r"[A-Za-z_]", lines[end]):
        end += 1
    return start, end


def _key_re(key):
    return re.compile(rf"^(\s+{key}:[ \t]*)([^#\n]*?)([ \t]*#.*)?$")


def config_get(text, section, key, default=None):
    lines = text.splitlines()
    start, end = _section(lines, section)
    for line in lines[start + 1:end]:
        m = _key_re(key).match(line)
        if m:
            value = m[2].strip()
            if value.startswith('"') and value.endswith('"'):
                return value[1:-1]
            if value in ("true", "false"):
                return value == "true"
            return int(value) if value.isdigit() else value
    return default


def config_set(text, section, key, value):
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    elif isinstance(value, int):
        rendered = str(value)
    elif re.fullmatch(r"[a-z][a-z0-9.\-]*", value) and value not in ("true", "false", "yes", "no", "null"):
        rendered = value
    else:
        rendered = json.dumps(value, ensure_ascii=False)
    lines = text.splitlines()
    start, end = _section(lines, section)
    for i in range(start + 1, end):
        m = _key_re(key).match(lines[i])
        if m:
            comment = m[3] or ""
            if comment:
                # Keep the comment in its column when there's room.
                column = len(m[2]) + len(comment) - len(comment.lstrip())
                comment = " " * max(1, column - len(rendered)) + comment.lstrip()
            lines[i] = m[1] + rendered + comment
            return "\n".join(lines) + "\n"
    last = max(i for i in range(start, end) if lines[i].strip())
    lines.insert(last + 1, f"  {key}: {rendered}")
    return "\n".join(lines) + "\n"


# ── Steps ───────────────────────────────────────────────────────────

def step(title):
    print(f"\n── {title} " + "─" * max(3, 60 - len(title)))


def ask_everything(env, config):
    answers = {"env": {}, "config": []}
    setc = lambda section, key, value: answers["config"].append((section, key, value))

    step("1/5 · Buzón de Gmail del boletín")
    print("  Hace falta una contraseña de aplicación de Google (con la verificación en dos pasos\n"
          "  activada): https://myaccount.google.com/apppasswords")
    address, password = checked(
        lambda: (ask("Dirección de Gmail", env.get("GMAIL_ADDRESS", ""), check_email),
                 ask_secret("Contraseña de aplicación", env.get("GMAIL_APP_PASSWORD", "")).replace(" ", "")),
        lambda creds: check_gmail(creds, env))
    answers["env"].update(GMAIL_ADDRESS=address, GMAIL_APP_PASSWORD=password)
    answers["env"]["ADMIN_EMAIL"] = ask(
        "Correo del administrador (recibe la prueba de cada mes)", env.get("ADMIN_EMAIL", ""), check_email)
    answers["inbox"] = address

    step("2/5 · Inteligencia artificial")
    provider = ask_choice("¿Qué servicio redacta el boletín?",
                          [("anthropic", "Claude (Anthropic)"), ("openai", "OpenAI")],
                          config_get(config, "llm", "provider", "anthropic"))
    current_model = config_get(config, "llm", "model", "")
    if provider == "anthropic":
        options = list(ANTHROPIC_MODELS)
        if current_model.startswith("claude") and current_model not in dict(options):
            options.append((current_model, f"{current_model} (el actual)"))
        model = ask_choice("Modelo:", options, current_model)
        key_name, key_hint = "ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys"
    else:
        model = ask("Modelo de OpenAI", "" if current_model.startswith("claude") else current_model)
        key_name, key_hint = "OPENAI_API_KEY", "https://platform.openai.com/api-keys"
    print(f"  La clave se crea en {key_hint}")
    answers["env"][key_name] = checked(
        lambda: ask_secret("Clave de la API", env.get(key_name, "")),
        lambda key: check_llm(provider, key))
    setc("llm", "provider", provider)
    setc("llm", "model", model)

    step("3/5 · Brevo")
    print("  Brevo → SMTP y API → Claves API: https://app.brevo.com/settings/keys/api")
    brevo = {}

    def check_brevo(key):
        ok, message, account = http_check("https://api.brevo.com/v3/account", {"api-key": key}, "Brevo")
        if ok:
            message = f"Brevo: cuenta de {account.get('email', '?')}."
            for path, field in (("/contacts/lists?limit=50", "lists"), ("/senders", "senders")):
                try:
                    brevo[field] = http_get(f"https://api.brevo.com/v3{path}", {"api-key": key}).get(field) or []
                except (OSError, ValueError):
                    brevo[field] = []
        return ok, message

    answers["env"]["BREVO_API_KEY"] = checked(
        lambda: ask_secret("Clave de la API de Brevo", env.get("BREVO_API_KEY", "")), check_brevo)

    current_list = config_get(config, "brevo", "list_id", 1)
    if brevo.get("lists"):
        list_id = ask_choice("¿A qué lista de contactos se envía el boletín?", [
            (l["id"], f"{l['name']} ({l.get('uniqueSubscribers', l.get('totalSubscribers', '?'))} contactos)")
            for l in brevo["lists"]], current_list)
    else:
        list_id = int(ask("Número (id) de la lista de contactos en Brevo", current_list,
                          lambda a: None if a.isdigit() else "Tiene que ser un número."))
    senders = [s for s in brevo.get("senders", []) if s.get("active")]
    current_sender = config_get(config, "brevo", "sender_email", "")
    if senders:
        chosen = ask_choice("¿Desde qué remitente se envía? (remitentes verificados en Brevo)",
                            [(s["email"], f"{s['name']} <{s['email']}>") for s in senders], current_sender)
        sender = next(s for s in senders if s["email"] == chosen)
        sender_name, sender_email = sender["name"], sender["email"]
    else:
        print("  No hay remitentes verificados que leer: escríbelo (tendrás que verificarlo en Brevo).")
        sender_name = ask("Nombre del remitente", config_get(config, "brevo", "sender_name", ""))
        sender_email = ask("Correo del remitente",
                           "" if is_placeholder(current_sender) else current_sender, check_email)
    setc("brevo", "list_id", list_id)
    setc("brevo", "sender_name", sender_name)
    setc("brevo", "sender_email", sender_email)

    step("4/5 · Calendario")
    print("  El ordenador puede estar apagado: lo que no se haga un día se hace la próxima vez\n"
          "  que se encienda (ver README, «Programarlo en Windows»).")
    get = lambda key, default: config_get(config, "schedule", key, default)
    start = int(ask("Día del mes en que se empiezan a recoger los correos",
                    get("collection_start_day", 10), check_day(1, 26)))
    reminder = int(ask("Día del recordatorio a los grupos que no han enviado",
                       get("reminder_day", 20), check_day(start, 27)))
    publish = int(ask("Día en que se prepara el borrador del boletín",
                      get("publish_day", 25), check_day(reminder + 1, 28)))
    hour, minute = ask("¿A qué hora se ejecuta cada día?", get("run_time", "10:00"), check_time).split(":")
    run_time = f"{int(hour):02d}:{minute}"
    every = int(ask("¿Repetir cada cuántas horas mientras el ordenador esté encendido? (0 = una vez al día)",
                    get("run_every_hours", 0),
                    lambda a: None if a.isdigit() and int(a) <= 12 else "Un número de 0 a 12."))
    at_logon = ask_yes("¿Ejecutarlo también al encender el ordenador? (recomendado si se apaga a diario)",
                       get("run_at_logon", True))
    for key, value in (("collection_start_day", start), ("reminder_day", reminder),
                       ("publish_day", publish), ("run_time", run_time),
                       ("run_every_hours", every), ("run_at_logon", at_logon)):
        setc("schedule", key, value)
    answers["schedule"] = (run_time, every, at_logon)
    return answers


def install_venv():
    if not VENV_PYTHON.exists():
        print("  Creando el entorno de Python (.venv)…")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    print("  Instalando las dependencias (puede tardar un par de minutos)…")
    subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "-q", "--disable-pip-version-check",
                    "-r", str(PROJECT_DIR / "requirements.txt")], check=True)
    print("  ✓ Entorno listo.")


def install_task(run_time, every, at_logon):
    if WINDOWS:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
               str(PROJECT_DIR / "scripts" / "install_windows_task.ps1"),
               "-At", run_time, "-EveryHours", str(every)]
        subprocess.run(cmd + ([] if at_logon else ["-NoLogon"]), check=True)
        return
    run = f"cd {shlex.quote(str(PROJECT_DIR))} && .venv/bin/python scripts/run_daily.py"
    hour, minute = (int(x) for x in run_time.split(":"))
    hours = f"{hour}-23/{every}" if every else str(hour)
    lines = [f"{minute} {hours} * * * {run} {CRON_MARK}"]
    if at_logon:
        lines.append(f"@reboot sleep 300 && {run} {CRON_MARK}")
    current = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    kept = [l for l in current.splitlines() if CRON_MARK not in l]
    subprocess.run(["crontab", "-"], input="\n".join(kept + lines) + "\n", text=True, check=True)
    print("  ✓ Añadido a cron:\n    " + "\n    ".join(lines))


def make_guide(inbox):
    subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "-q", "--disable-pip-version-check",
                    "reportlab"], check=True)
    subprocess.run([str(VENV_PYTHON), str(PROJECT_DIR / "docs" / "make_plantilla.py"), "--to", inbox],
                   check=True)


def main():
    if sys.version_info < (3, 11):
        sys.exit(f"Hace falta Python 3.11 o posterior (este es {sys.version.split()[0]}).")
    if sys.stdout is not None:
        sys.stdout.reconfigure(errors="replace")

    print("\n  Instalación del boletín parroquial")
    print("  Pulsa Intro para dejar el valor que aparece entre corchetes.")
    env = read_env()
    config = CONFIG_FILE.read_text(encoding="utf-8")
    answers = ask_everything(env, config)

    step("5/5 · Instalación")
    if not ask_yes("¿Guardar todo esto e instalar?"):
        sys.exit("  No se ha cambiado nada.")

    write_env(answers["env"])
    for section, key, value in answers["config"]:
        config = config_set(config, section, key, value)
    CONFIG_FILE.write_text(config, encoding="utf-8")
    print("  ✓ Claves guardadas en .env y ajustes en config.yaml.")

    install_venv()

    try:
        install_task(*answers["schedule"])
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"  ! No se pudo crear la tarea programada ({e}). Ver README, «Programarlo en Windows».")

    if ask_yes("¿Generar la guía en PDF para los secretarios con la dirección del buzón?"):
        try:
            make_guide(answers["inbox"])
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"  ! No se pudo generar la guía ({e}).")

    placeholders = len(re.findall(r"secretary_email:\s*\"?[^\s\"]*@example\.com", config))
    print("\n  Instalación terminada.")
    if placeholders:
        cli = (r".venv\Scripts\python scripts\newsletter-cli.py" if WINDOWS
               else ".venv/bin/python scripts/newsletter-cli.py")
        print(f"  ! {placeholders} grupo(s) tienen aún una dirección de ejemplo (@example.com).\n"
              f"    Pon la de cada secretario en config.yaml o con: {cli}")
    print("  Lo que haga cada día queda en logs/AAAA-MM.log.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\n  Instalación cancelada.")
