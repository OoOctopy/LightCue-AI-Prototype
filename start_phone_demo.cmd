@echo off
title LightCue Phone Screen Demo
cd /d "%~dp0"
echo LightCue phone screen demo
echo.
echo Computer: http://127.0.0.1:8765/
echo Phone: http://COMPUTER-IP:8765/screen
echo Keep this window open while testing. Press Ctrl+C to stop.
echo Replace COMPUTER-IP with your computer's Wi-Fi or USB network IPv4 address.
echo.
set "LIGHTCUE_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%LIGHTCUE_PYTHON%" (
  "%LIGHTCUE_PYTHON%" phone_demo.py --host 0.0.0.0 --port 8765
) else (
  python phone_demo.py --host 0.0.0.0 --port 8765
)
echo.
echo Service stopped or could not start. Check the message above.
echo If port 8765 is already in use, do not close another app blindly.
pause
