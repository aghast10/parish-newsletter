@echo off
rem Installer for Windows: double-click it. Runs scripts\install.py with Python,
rem installing Python first with winget if it is missing.
chcp 65001 >nul
cd /d "%~dp0"

where py >/dev/null 2>nul
if errorlevel 1 (
    echo No se encuentra Python. Instalandolo con winget...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo.
        echo No se ha podido instalar. Descarga Python 3.12 de https://www.python.org/downloads/
        echo e instalalo; luego vuelve a abrir este archivo.
        pause
        exit /b 1
    )
    echo.
    echo Python instalado. Cierra esta ventana y vuelve a abrir instalar.bat.
    pause
    exit /b 0
)

py -3 scripts\install.py
echo.
pause
