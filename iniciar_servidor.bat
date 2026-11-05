@echo off
cd /d "%~dp0servidor"
where py >nul 2>nul
if errorlevel 1 (set "PYTHON=python") else (set "PYTHON=py -3")
%PYTHON% -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>nul
if errorlevel 1 (
    echo Se requiere Python 3.12 o superior instalado y disponible en PATH.
    exit /b 1
)
if not exist .venv\Scripts\python.exe %PYTHON% -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8080
