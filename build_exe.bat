@echo off
rem Builds dist\AoE2-Counter-Overlay.exe (single file, no Python needed to run it).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe python -m venv .venv
.venv\Scripts\python.exe -m pip install -q -r requirements.txt pyinstaller || goto :fail
.venv\Scripts\python.exe tools\check_data.py || goto :fail
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name AoE2-Counter-Overlay --collect-submodules websockets ^
  --add-data "data\techtree;data\techtree" ^
  --add-data "data\civ_tips.en.json;data" ^
  --add-data "data\maps.en.json;data" ^
  --add-data "data\maps_official.json;data" ^
  --add-data "data\unit_texts_game.json;data" ^
  run_overlay.py || goto :fail
echo.
echo Done: dist\AoE2-Counter-Overlay.exe
goto :eof
:fail
echo Build failed.
pause
