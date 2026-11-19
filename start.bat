@echo off
rem Starts the overlay (live mode). First run sets up .venv (needs Python 3.12+ on PATH).
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  echo Setting up, this takes 1-2 minutes ...
  python -m venv .venv || goto :nopython
  .venv\Scripts\python.exe -m pip install -q -r requirements.txt || goto :eof
)
start "" .venv\Scripts\pythonw.exe -m aoe2overlay %*
goto :eof
:nopython
echo Python not found. Install Python 3.12 from python.org and tick "Add python.exe to PATH".
pause
