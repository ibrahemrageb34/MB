@echo off
REM Daily run on a Windows PC until the server is ready.
REM Task Scheduler -> Create Basic Task -> Daily 08:00 -> Start a program -> this file.
cd /d "%~dp0\.."
python -m mbos run
python -m mbos alerts --kind prepaid
start "" "output\dashboard.html"
