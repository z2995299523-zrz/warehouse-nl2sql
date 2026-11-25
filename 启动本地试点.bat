@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PILOT_SCRIPT=.runtime-deploy\pilot-access-phase1-20261111\start-fixed.ps1"
if not exist "%PILOT_SCRIPT%" (
    echo Local pilot package missing. Run start.bat for normal setup.
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PILOT_SCRIPT%"
if errorlevel 1 pause
