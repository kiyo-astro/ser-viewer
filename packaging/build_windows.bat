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

REM Name the archive after the version, the way the macOS DMG is named.
for /f "delims=" %%v in ('%PYTHON% -c "import runpy;print(runpy.run_path('serview/__init__.py')['__version__'])"') do set VERSION=%%v
echo !VERSION!| findstr /r /c:"^[0-9][0-9.]*$" >nul
if errorlevel 1 (
    echo Could not read a sensible version from serview\__init__.py: "!VERSION!"
    exit /b 1
)
set ZIP=dist\SER-Viewer-!VERSION!-windows-x64.zip

powershell -NoProfile -Command "Compress-Archive -Path 'dist/SER Viewer/*' -DestinationPath '!ZIP!' -Force" || exit /b 1

echo.
echo Built "dist\SER Viewer\SER Viewer.exe"
echo Built !ZIP!
