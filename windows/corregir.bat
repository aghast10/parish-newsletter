@echo off
rem Re-compose with the admin's notes and update the Brevo draft (scripts\correct.py).
chcp 65001 >nul
cd /d "%~dp0.."
.venv\Scripts\python scripts\correct.py
pause
