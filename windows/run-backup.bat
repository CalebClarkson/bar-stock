@echo off
cd /d "%~dp0.."
.venv\Scripts\python.exe manage.py backup >> data\backup.log 2>&1
