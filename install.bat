@echo off
rem Storyteller installer. Safe to run again: it repairs and updates an existing install.
setlocal EnableExtensions
cd /d "%~dp0"
title Storyteller setup
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"

echo.
echo   Storyteller setup
echo   -----------------
echo   This installs everything Storyteller needs to read your PDFs aloud.
echo   The first run downloads about 3 GB and can take 10 to 20 minutes.
echo   Later runs only fetch what changed. Keep this window open until it says Done.
echo.

rem ---- 1. uv: installs Python and the packages ---------------------------------
echo [1/4] Checking the installer tool, uv...
where uv >nul 2>nul
if not errorlevel 1 goto :have_uv
echo       Not found. Downloading uv from astral.sh...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
where uv >nul 2>nul
if errorlevel 1 goto :fail_uv
:have_uv
echo       OK.
echo.

rem ---- 2. Python and packages ----------------------------------------------------
echo [2/4] Installing Python and the reader's packages. This is the long step...
uv sync --extra voice
if errorlevel 1 goto :fail_sync
echo       OK.
echo.

rem ---- 3. Voice model -----------------------------------------------------------
echo [3/4] Setting up the voice...
uv run --no-sync python -m storyteller setup
if errorlevel 1 goto :fail_voice
echo.

rem ---- 4. Shortcuts -------------------------------------------------------------
echo [4/4] Adding Storyteller to the desktop and the Start menu...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\shortcuts.ps1"
if errorlevel 1 goto :fail_shortcut
echo       OK.
echo.

echo   Done. Open Storyteller from the desktop or the Start menu.
echo   To update or repair later, run install.bat again.
echo.
pause
exit /b 0

:fail_uv
echo.
echo   Could not install uv. Check your internet connection and run install.bat again.
echo   You can also install uv by hand from https://docs.astral.sh/uv/ and then rerun this.
goto :failed

:fail_sync
echo.
echo   Installing the packages failed. The messages above say which one.
echo   Check your internet connection and free disk space, about 5 GB, then run install.bat again.
goto :failed

:fail_voice
echo.
echo   The voice could not be set up. The message above says why.
goto :failed

:fail_shortcut
echo.
echo   Storyteller is installed, but the shortcuts could not be created.
echo   You can start it any time by double-clicking run.bat in this folder.
goto :failed

:failed
echo.
pause
exit /b 1
