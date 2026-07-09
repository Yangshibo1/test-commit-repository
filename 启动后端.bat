@echo off
setlocal EnableDelayedExpansion
title OpenTrace Backend

echo ======================================
echo     OpenTrace Backend
echo ======================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: python not found in PATH
    echo Please install Python or use full path
    echo.
    pause
    exit /b 1
)

cd /d "%~dp0VAST_Challenge_2026_MC2"

if not exist "%~dp0VAST_Challenge_2026_MC2" (
    echo Error: backend directory not found
    echo.
    pause
    exit /b 1
)

echo Generating data artifacts...
echo.

python generate_artifacts.py

echo.
echo ======================================
if %ERRORLEVEL% equ 0 (
    echo Artifact generation completed!
) else (
    echo Artifact generation failed, check errors above
)
echo.
pause
endlocal
