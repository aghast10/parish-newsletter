@echo off
rem Windows fallback (README, "Alternativa: un ordenador con Windows"): creates
rem .venv, opens .env to fill in the keys and registers the daily runs.
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

if not exist .env copy .env.example .env >nul
echo.
echo Se abre .env en el Bloc de notas: escribe las claves, guarda y cierra.
start "" notepad .env
pause

powershell -NoProfile -ExecutionPolicy Bypass -File windows\tarea.ps1 || goto error
echo.
echo Listo. Cada dia a las 10:00 y al iniciar sesion se hace lo que toque.
echo Lo que haga queda en la carpeta logs.
pause
exit /b 0

:error
echo.
echo Algo ha fallado: revisa los mensajes de arriba.
pause
exit /b 1
