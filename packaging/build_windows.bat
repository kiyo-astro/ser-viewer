@echo off
REM Build SER Viewer for Windows. Run from the project root:
REM     packaging\build_windows.bat
setlocal enabledelayedexpansion
cd /d "%~dp0.."

set PYTHON=python
if "%1"=="--venv" (
    rmdir /s /q .buildenv 2>nul
    %PYTHON% -m venv .buildenv || exit /b 1
    set PYTHON=.buildenv\Scripts\python.exe
    !PYTHON! -m pip install --upgrade pip || exit /b 1
    !PYTHON! -m pip install -r requirements-dev.txt || exit /b 1
)

%PYTHON% packaging\make_icon.py || exit /b 1
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
%PYTHON% -m PyInstaller --noconfirm --clean packaging\serview.spec || exit /b 1

if not exist "dist\SER Viewer\SER Viewer.exe" (
    echo The Windows build did not produce "SER Viewer.exe"
    exit /b 1
)

powershell -NoProfile -Command "Compress-Archive -Path 'dist/SER Viewer/*' -DestinationPath 'dist/SER-Viewer-windows.zip' -Force" || exit /b 1

echo.
echo Built "dist\SER Viewer\SER Viewer.exe"
echo Built dist\SER-Viewer-windows.zip
