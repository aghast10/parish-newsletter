@echo off
rem Runs scripts\brevo_relay.py now, for example right after a correction.
chcp 65001 >nul
cd /d "%~dp0.."
.venv\Scripts\python scripts\brevo_relay.py
pause
