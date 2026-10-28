@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Shiwu x Customer Meow - http://127.0.0.1:8000
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run.py
) else if exist "..\graph2\python.exe" (
  "..\graph2\python.exe" run.py
) else (
  python run.py
)
pause
