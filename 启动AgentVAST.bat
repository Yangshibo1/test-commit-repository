@echo off
setlocal EnableExtensions
chcp 65001 >nul

title AgentVAST Launcher

set "ROOT_DIR=%~dp0"
set "FRONTEND_DIR=%ROOT_DIR%frontend"
set "PRIMARY_PROJECT_DIR=%ROOT_DIR%VAST_Challenge_2026_MC2"
set "LEGACY_PROJECT_DIR=%ROOT_DIR%VAST_Challenge_2026_MC2（1）\VAST_Challenge_2026_MC2"
set "PROJECT_DIR=%PRIMARY_PROJECT_DIR%"
set "DIAGNOSE_ONLY=0"
set "CUSTOM_PROJECT=0"

cd /d "%ROOT_DIR%"
if errorlevel 1 (
    echo [ERROR] Cannot enter the AgentVAST repository directory:
    echo %ROOT_DIR%
    goto :failed
)

if /I "%~1"=="--diagnose" (
    set "DIAGNOSE_ONLY=1"
    if not "%~2"=="" (
        set "PROJECT_DIR=%~f2"
        set "CUSTOM_PROJECT=1"
    )
) else (
    if not "%~1"=="" (
        set "PROJECT_DIR=%~f1"
        set "CUSTOM_PROJECT=1"
    )
)

if "%CUSTOM_PROJECT%"=="0" if not exist "%PROJECT_DIR%" if exist "%LEGACY_PROJECT_DIR%" set "PROJECT_DIR=%LEGACY_PROJECT_DIR%"

echo ======================================
echo          AgentVAST Launcher
echo ======================================
echo Repository: %ROOT_DIR%
echo Project:    %PROJECT_DIR%
echo.

if not exist "%PROJECT_DIR%" (
    echo [ERROR] Analysis project directory does not exist:
    echo %PROJECT_DIR%
    echo.
    echo Pass a valid project directory as the first argument.
    goto :failed
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo [ERROR] Frontend directory is incomplete:
    echo %FRONTEND_DIR%
    goto :failed
)

where python.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python.exe is not available in PATH.
    goto :failed
)

echo [CHECK] AgentVAST source import...
python -c "import agentvast; print(agentvast.__file__)"
if errorlevel 1 (
    echo [ERROR] AgentVAST cannot be imported from this repository.
    goto :failed
)

echo [CHECK] Web backend dependencies...
python -c "import fastapi, uvicorn, winpty; print('FastAPI, Uvicorn and WinPTY are available')"
if errorlevel 1 (
    echo [ERROR] AgentVAST Web dependencies cannot be loaded.
    echo Install them with: python -m pip install -e ".[web]"
    echo If the error is WinError 10106, open Command Prompt as Administrator, run:
    echo   netsh winsock reset
    echo Then restart Windows and run --diagnose again.
    goto :failed
)

echo [CHECK] Frontend runtime...
where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm.cmd is not available in PATH. Install Node.js and reopen this script.
    goto :failed
)
call npm.cmd --version >nul
if errorlevel 1 (
    echo [ERROR] npm.cmd was found but cannot run. Repair the Node.js installation.
    goto :failed
)

echo [CHECK] Claude Code...
where claude.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] claude.exe is not available in PATH. Install and sign in to Claude Code.
    goto :failed
)
claude.exe --version >nul
if errorlevel 1 (
    echo [ERROR] claude.exe was found but cannot start. Repair or reinstall Claude Code.
    goto :failed
)

if "%DIAGNOSE_ONLY%"=="1" (
    echo.
    echo [OK] All AgentVAST launcher checks passed.
    echo Run this script without --diagnose to start the services.
    exit /b 0
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo Installing frontend dependencies...
    call npm.cmd --prefix "%FRONTEND_DIR%" install
    if errorlevel 1 (
        echo [ERROR] Frontend dependency installation failed.
        goto :failed
    )
)

echo Stopping previous AgentVAST services on ports 8765 and 3000 ...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ports = @(8765, 3000); Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort } | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
if errorlevel 1 (
    echo [ERROR] Could not inspect or stop the previous AgentVAST services.
    echo Close the existing backend/frontend windows, then run this script again.
    goto :failed
)
timeout /t 1 /nobreak >nul

echo Starting AgentVAST backend at http://127.0.0.1:8765 ...
start "AgentVAST Backend" /D "%ROOT_DIR%" cmd.exe /k python -m agentvast.cli web --project "%PROJECT_DIR%"

timeout /t 3 /nobreak >nul

set "AGENTVAST_LAUNCH_PROJECT=%PROJECT_DIR%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $response = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 3; if (-not $response -or [int]$response.api_version -lt 2) { exit 1 }; $actual = [IO.Path]::GetFullPath([string]$response.default_project).TrimEnd('\'); $expected = [IO.Path]::GetFullPath($env:AGENTVAST_LAUNCH_PROJECT).TrimEnd('\'); if ($actual -ine $expected) { Write-Error ('Backend project mismatch. Expected: ' + $expected + '; actual: ' + $actual); exit 2 } } catch { Write-Error $_; exit 1 }"
if errorlevel 1 (
    echo [ERROR] Backend health check failed.
    echo Review the "AgentVAST Backend" window for the complete error.
    goto :failed
)

echo Starting AgentVAST frontend at http://localhost:3000 ...
start "AgentVAST Frontend" /D "%FRONTEND_DIR%" cmd.exe /k npm.cmd run dev

echo.
echo [OK] AgentVAST services are starting in two terminal windows.
echo Backend: http://127.0.0.1:8765
echo Frontend: http://localhost:3000
echo Close the service windows or press Ctrl+C in each one to stop.
exit /b 0

:failed
echo.
echo AgentVAST did not start. Fix the error above, then run:
echo   "%~nx0" --diagnose
echo.
pause
exit /b 1
