@echo off
title AI Translate
cd /d "%~dp0"

set PY_CMD=
:: Try python first
python --version >nul 2>&1
if %errorlevel% equ 0 set PY_CMD=python
:: Try py launcher
if "%PY_CMD%"=="" (
    py --version >nul 2>&1
    if %errorlevel% equ 0 set PY_CMD=py
)
:: Try full path
if "%PY_CMD%"=="" (
    if exist "C:\Users\%USERNAME%\AppData\Local\Python\bin\python.exe" (
        set PY_CMD=C:\Users\%USERNAME%\AppData\Local\Python\bin\python.exe
    )
)

if "%PY_CMD%"=="" (
    echo Python not found. Please install Python 3 first.
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Using: %PY_CMD%
echo.

:: Check and install dependencies
%PY_CMD% -c "import PySide6" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing dependencies...
    %PY_CMD% -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo Dependency installation failed.
        pause
        exit /b 1
    )
)

echo Starting AI Translate...
%PY_CMD% main.py
pause
