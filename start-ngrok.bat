@echo off
setlocal
cd /d "%~dp0"
title BetPawa Predictor - ngrok tester link
where ngrok >nul 2>&1
if errorlevel 1 (
  echo.
  echo ngrok was not found on your PATH.
  echo Download ngrok for Windows: https://ngrok.com/download/windows
  echo Create an ngrok account, then in PowerShell run:
  echo   ngrok config add-authtoken YOUR_NGROK_AUTHTOKEN
  echo.
  echo Restart this script after installing and configuring ngrok.
  pause
  exit /b 1
)
echo.
echo Start run.bat first and leave the predictor server running on port 8010.
echo This window will display your public HTTPS ngrok URL.
echo Only invite trusted adults aged 25+ during supervised testing.
echo Anyone with the URL can reach the login page; never share your admin password.
echo Keep this window open for as long as testers need access.
echo.
ngrok http 8010
echo.
echo ngrok stopped. The public tester link is no longer available.
pause
