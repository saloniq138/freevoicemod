@echo off
setlocal
cd /d "%~dp0"
echo [1/4] Creating virtual environment...
py -3.12 -m venv .venv
if errorlevel 1 goto error
call .venv\Scripts\activate.bat
echo [2/4] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error
echo [3/4] Building VoiceForge.exe...
python -m PyInstaller --noconfirm --clean --windowed --name VoiceForge --collect-all sounddevice --collect-all PySide6 main.py
if errorlevel 1 goto error
echo [4/4] DONE: dist\VoiceForge\VoiceForge.exe
echo Keep the complete dist\VoiceForge folder together.
pause
exit /b 0
:error
echo BUILD FAILED. Read the error above.
pause
exit /b 1
