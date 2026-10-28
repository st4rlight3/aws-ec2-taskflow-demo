@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "BUNDLED_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED_PYTHON%" (
  "%BUNDLED_PYTHON%" app.py --open-browser
  pause
  exit /b
)
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 app.py --open-browser
  pause
  exit /b
)
where python >nul 2>nul
if %errorlevel% equ 0 (
  python app.py --open-browser
  pause
  exit /b
)
echo Can cai Python 3.10 tro len tu https://www.python.org/downloads/
pause
