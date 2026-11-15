@echo off
rem Starts Storyteller and opens it in the browser. If it is already running, just opens the browser.
setlocal EnableExtensions
cd /d "%~dp0"
title Storyteller
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
rem Fully offline after install: use the voice files that setup downloaded, never re-check online.
set "HF_HUB_OFFLINE=1"

where uv >nul 2>nul
if errorlevel 1 goto :not_installed
if not exist ".venv\" goto :not_installed

rem --no-sync: never touch the network or change packages on launch.
uv run --no-sync python -m storyteller serve
if errorlevel 1 (
  echo.
  pause
)
exit /b

:not_installed
echo Storyteller isn't installed yet. Double-click install.bat in this folder first.
echo.
pause
exit /b 1
