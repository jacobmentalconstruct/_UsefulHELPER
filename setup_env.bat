@echo off
setlocal

if not exist ".venv" (
    py -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip

if exist "requirements.txt" (
    pip install -r requirements.txt
)

endlocal
