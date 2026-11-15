@echo off
rem Removes the shortcuts and the installed packages. Your packs and settings are kept.
setlocal EnableExtensions
cd /d "%~dp0"
title Uninstall Storyteller
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"

echo.
echo   This removes the Storyteller shortcuts and its installed packages.
echo   Your packs, reading positions and settings are kept.
echo.
choice /c YN /m "  Uninstall Storyteller"
if errorlevel 2 exit /b 0

set "DATA="
if exist ".venv\" for /f "usebackq delims=" %%D in (`uv run --no-sync python -m storyteller where 2^>nul`) do set "DATA=%%D"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\shortcuts.ps1" -Remove
if exist ".venv\" rmdir /s /q ".venv"

echo.
echo   Storyteller is uninstalled. To install it again, run install.bat.
if defined DATA echo   Your packs and settings are still in: %DATA%
echo   Delete that folder too if you want to remove them.
echo.
pause
