@echo off
REM ============================================================
REM  Knowledge Graph System - Windows one-click launcher
REM  Usage:
REM    start.bat          start all services
REM    start.bat stop     stop all services
REM    start.bat status   show port status
REM ============================================================
setlocal enabledelayedexpansion

REM ---------- Config (edit these paths to match your machine) ----------
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "LLAMA_SERVER=D:\llama.cpp\build\bin\llama-server.exe"
set "PYTHON=python"
set "MODEL_DIR=%PROJECT_DIR%\model\gemma-4-12b-uncensored"
set "MAIN_MODEL=%MODEL_DIR%\Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf"
set "DRAFT_MODEL=%MODEL_DIR%\mtp-gemma-4-12B-it.gguf"
set "MODEL_ALIAS=gemma-4-12b-uncensored"
set "LOG_DIR=%PROJECT_DIR%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

if "%~1"=="stop"   goto stop_all
if "%~1"=="status" goto show_status

REM ---------- sanity check ----------
if not exist "%LLAMA_SERVER%" (
    echo [ERROR] llama-server.exe not found: %LLAMA_SERVER%
    echo         Please edit the LLAMA_SERVER path at the top of start.bat
    pause
    goto :eof
)
if not exist "%MAIN_MODEL%" (
    echo [ERROR] model file not found: %MAIN_MODEL%
    echo         Run down.py first to download the GGUF weights.
    pause
    goto :eof
)

REM ---------- llama-server (:8000) ----------
echo [start] llama-server on :8000 ...
start "kg-llm" /min "" "%LLAMA_SERVER%" ^
    -m "%MAIN_MODEL%" ^
    -md "%DRAFT_MODEL%" --spec-type draft-mtp ^
    --alias "%MODEL_ALIAS%" ^
    --host 127.0.0.1 --port 8000 ^
    --ctx-size 16384 --n-gpu-layers 99 -fa on

REM ---------- backend (:3000) ----------
echo [start] backend on :3000 ...
start "kg-backend" /min cmd /c "cd /d %PROJECT_DIR% && %PYTHON% -m uvicorn main:app --host 127.0.0.1 --port 3000 > %LOG_DIR%\backend.log 2>&1"

REM ---------- frontend (:5173) ----------
echo [start] frontend on :5173 ...
start "kg-frontend" /min cmd /c "cd /d %PROJECT_DIR%\frontend && npm run dev > %LOG_DIR%\frontend.log 2>&1"

echo.
echo All services are starting in minimized windows.
echo Frontend: http://127.0.0.1:5173
echo First launch may be slow while the model loads (~30s).
echo Run "start.bat status" to check ports.
goto :eof

:stop_all
echo [stop] killing all services ...
taskkill /fi "WINDOWTITLE eq kg-llm*"      /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq kg-backend*"  /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq kg-frontend*" /f >nul 2>&1
REM fallback: kill by process name
taskkill /im llama-server.exe /f >nul 2>&1
taskkill /im node.exe /f >nul 2>&1
echo Done.
goto :eof

:show_status
echo [status] checking ports ...
netstat -ano | findstr ":8000 " | findstr LISTENING >nul && (echo   llama-server :8000  RUNNING) || (echo   llama-server :8000  STOPPED)
netstat -ano | findstr ":3000 " | findstr LISTENING >nul && (echo   backend      :3000  RUNNING) || (echo   backend      :3000  STOPPED)
netstat -ano | findstr ":5173 " | findstr LISTENING >nul && (echo   frontend     :5173  RUNNING) || (echo   frontend     :5173  STOPPED)
goto :eof
