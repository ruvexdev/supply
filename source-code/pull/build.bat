@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python was not found on PATH. & pause & exit /b 1)

echo [1/3] Installing build dependencies...
python -m pip install --upgrade pip
python -m pip install --upgrade "yt-dlp[default]" pyinstaller || (pause & exit /b 1)

echo [2/3] Building Pull.exe (onefile)...
python -m PyInstaller --noconfirm --clean Pull.spec || (pause & exit /b 1)

echo [3/3] Done. Your file is: dist\Pull.exe
pause
