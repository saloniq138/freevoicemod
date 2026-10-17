@echo off
setlocal
cd /d "%~dp0"
echo [1/5] Creating virtual environment...
py -3.12 -m venv .venv
if errorlevel 1 goto error
call .venv\Scripts\activate.bat
echo [2/5] Installing dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto error
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error
echo [3/5] Running hardware-independent tests...
python -m unittest discover -s tests -v
if errorlevel 1 goto error
echo [4/5] Building VoiceForge.exe...
python -m PyInstaller --noconfirm --clean --windowed --name VoiceForge --collect-all sounddevice --collect-all PySide6 --collect-all miniaudio --add-data "Villager_hurt1.ogg.zip;." main.py
if errorlevel 1 goto error
echo [5/5] DONE: dist\VoiceForge\VoiceForge.exe
echo Keep the complete dist\VoiceForge folder together.
pause
exit /b 0
:error
echo BUILD FAILED. Read the error above.
pause
exit /b 1
