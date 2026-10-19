@echo off
rem Plan B for Brevo (README, "Plan B: subir a Brevo desde Windows"): creates .venv,
rem asks for the keys in .env and schedules scripts\brevo_relay.py every hour.
chcp 65001 >nul
cd /d "%~dp0.."

where py >nul 2>nul
if errorlevel 1 (
    echo No se encuentra Python. Instalandolo con winget...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo No se ha podido. Instala Python 3.12 desde https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo Python instalado. Cierra esta ventana y vuelve a abrir instalar.bat.
    pause
    exit /b 0
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 (
    echo Hace falta Python 3.11 o posterior: https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist .venv\Scripts\python.exe (
    echo Creando el entorno de Python...
    py -3 -m venv .venv || goto error
)
echo Instalando las dependencias...
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt || goto error

if not exist .env (
    > .env echo # Claves para subir a Brevo desde este ordenador. Ver el README.
    >> .env echo GITHUB_REPO=usuario/repositorio-privado
    >> .env echo GITHUB_TOKEN=
    >> .env echo BREVO_API_KEY=
    >> .env echo ADMIN_EMAIL=
)
echo.
echo Se abre .env en el Bloc de notas: escribe las claves, guarda y cierra.
start "" notepad .env
pause

powershell -NoProfile -ExecutionPolicy Bypass -File windows\tarea.ps1 || goto error
echo.
echo Primera comprobacion:
.venv\Scripts\python scripts\brevo_relay.py
echo.
echo Listo. Cada hora, mientras el ordenador este encendido, sube a Brevo lo que GitHub no haya podido.
pause
exit /b 0

:error
echo.
echo Algo ha fallado: revisa los mensajes de arriba.
pause
exit /b 1
