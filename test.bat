@echo off
cd /d "%~dp0"
title BetPawa Predictor Tests

echo Running BetPawa Predictor automated tests...
python -m unittest discover -s tests -v
if errorlevel 1 (
  echo.
  echo TESTS FAILED
  pause
  exit /b 1
)

echo.
echo ALL TESTS PASSED
pause
