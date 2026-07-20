@echo off
cd /d "%~dp0.."
set PYTHONDONTWRITEBYTECODE=1
python scripts\monitorar_auditoria.py
pause
