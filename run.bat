@echo off
cd /d "%~dp0"
title BetPawa Predictor

echo Installing/updating required packages...
python -m pip install -r requirements.txt
if errorlevel 1 pause & exit /b 1

echo.
echo Starting BetPawa Predictor at http://127.0.0.1:8010
start "" http://127.0.0.1:8010
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
pause