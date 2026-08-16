@echo off
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
