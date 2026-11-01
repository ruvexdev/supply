@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python was not found on PATH. & pause & exit /b 1)

echo [1/2] Installing PyInstaller...
python -m pip install --upgrade pip
python -m pip install --upgrade pyinstaller || (pause & exit /b 1)

echo [2/2] Building Stash.exe (onefile)...
python -m PyInstaller --noconfirm --clean Stash.spec || (pause & exit /b 1)

echo.
echo Done. Your file is: dist\Stash.exe
pause
