@echo off
setlocal EnableExtensions

cd /d "%~dp0\.."
if errorlevel 1 exit /b 1

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python launcher "py" was not found. Install Python 3.12 x64 first.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1

python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
python -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1

python -m pytest
if errorlevel 1 (
  echo [ERROR] Tests failed. Packaging stopped.
  exit /b 1
)

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name AutoVideoEditor ^
  --paths src ^
  scripts\windows_entry.py
if errorlevel 1 exit /b 1

copy /Y README.md "dist\AutoVideoEditor\README.md" >nul
echo.
echo Build complete: %CD%\dist\AutoVideoEditor\AutoVideoEditor.exe
echo FFmpeg and FFprobe remain external prerequisites; configure them in the application or PATH.
exit /b 0
