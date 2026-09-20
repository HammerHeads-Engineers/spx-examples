@REM SPDX-License-Identifier: MIT
@echo off
setlocal

cd /d "%~dp0"

set "SCRIPT="
for /f "delims=" %%F in ('dir /b /a:-d /o:-d spx-installer-*.ps1 2^>nul') do (
  if not defined SCRIPT set "SCRIPT=%%F"
)

if not defined SCRIPT (
  if exist "spx-install.ps1" (
    set "SCRIPT=spx-install.ps1"
  ) else (
    echo [spx-setup] No spx-installer-*.ps1 or spx-install.ps1 found.
    echo Exit code: 1
    pause
    exit /b 1
  )
)

powershell -ExecutionPolicy Bypass -NoProfile -File "%SCRIPT%"
set "EXITCODE=%ERRORLEVEL%"
echo Exit code: %EXITCODE%
pause
exit /b %EXITCODE%
