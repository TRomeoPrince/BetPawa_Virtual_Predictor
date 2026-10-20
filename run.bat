@echo off
cd /d "%~dp0"
title BetPawa Predictor

echo Installing/updating required packages...
python -m pip install -r requirements.txt
if errorlevel 1 pause & exit /b 1

echo.
echo Stopping any older BetPawa Predictor process on port 8010...
for /f "tokens=5" %%P in ('netstat -aon ^| findstr ":8010" ^| findstr "LISTENING"') do (
    taskkill /PID %%P /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo.
echo Starting BetPawa Predictor v0.3.10 at http://127.0.0.1:8010
start "" "http://127.0.0.1:8010/?v=0.3.10"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
pause
