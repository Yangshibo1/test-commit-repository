@echo off
setlocal EnableDelayedExpansion
title OpenTrace Frontend

echo ======================================
echo     OpenTrace Frontend
echo ======================================
echo.

set "NPM_CMD=C:\Program Files\nodejs\npm.cmd"
set "NODE_CMD=C:\Program Files\nodejs\node.exe"

if not exist "!NPM_CMD!" (
    echo Error: npm not found at !NPM_CMD!
    echo Please check Node.js installation
    echo.
    pause
    exit /b 1
)

cd /d "%~dp0frontend"

if not exist "%~dp0frontend" (
    echo Error: frontend directory not found
    echo.
    pause
    exit /b 1
)

echo npm path: !NPM_CMD!
echo Starting dev server...
echo URL: http://localhost:5173
echo.
echo Press Ctrl+C to stop
echo ======================================
echo.

if not exist "%~dp0frontend\node_modules" (
    echo First run, installing dependencies...
    call "!NPM_CMD!" install
    if %ERRORLEVEL% neq 0 (
        echo Error: dependency installation failed
        pause
        exit /b 1
    )
)

call "!NPM_CMD!" run dev

echo.
echo Server stopped
pause
endlocal
