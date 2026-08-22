@echo off
setlocal
chcp 65001 >nul

title AgentVAST Launcher

set "ROOT_DIR=%~dp0"
set "FRONTEND_DIR=%ROOT_DIR%frontend"
set "DEFAULT_PROJECT_DIR=%ROOT_DIR%VAST_Challenge_2026_MC2（1）\VAST_Challenge_2026_MC2"
set "PROJECT_DIR=%DEFAULT_PROJECT_DIR%"

if not "%~1"=="" set "PROJECT_DIR=%~f1"

echo ======================================
echo          AgentVAST Launcher
echo ======================================
echo Project: %PROJECT_DIR%
echo.

if not exist "%PROJECT_DIR%" (
    echo Error: project directory does not exist:
    echo %PROJECT_DIR%
    echo.
    echo You may pass another project directory as the first argument.
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo Error: frontend directory is incomplete:
    echo %FRONTEND_DIR%
    pause
    exit /b 1
)

where agentvast >nul 2>&1
if errorlevel 1 (
    echo Error: agentvast command is not available.
    echo Run this once from the repository root:
    echo python -m pip install -e ".[web]"
    pause
    exit /b 1
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo Error: npm.cmd is not available in PATH.
    echo Install Node.js and restart this script.
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo Installing frontend dependencies...
    call npm.cmd --prefix "%FRONTEND_DIR%" install
    if errorlevel 1 (
        echo Error: frontend dependency installation failed.
        pause
        exit /b 1
    )
)

echo Stopping previous AgentVAST services on ports 8765 and 3000 ...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ports = @(8765, 3000); Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue ^| Where-Object { $ports -contains $_.LocalPort } ^| Select-Object -ExpandProperty OwningProcess -Unique ^| ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
timeout /t 1 /nobreak >nul

echo Starting AgentVAST backend at http://127.0.0.1:8765 ...
start "AgentVAST Backend" /D "%ROOT_DIR%" cmd.exe /c agentvast web --project "%PROJECT_DIR%"

timeout /t 2 /nobreak >nul

echo Starting AgentVAST frontend at http://localhost:3000 ...
start "AgentVAST Frontend" /D "%FRONTEND_DIR%" cmd.exe /c npm.cmd run dev

echo.
echo AgentVAST is starting in two terminal windows.
echo Close those windows or press Ctrl+C in each one to stop the services.
echo.
exit /b 0
