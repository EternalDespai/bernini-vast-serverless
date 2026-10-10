@echo off
cd /d "%~dp0"
set "PYTHON=C:\AI\ComfyUI_windows_portable\python_embeded\python.exe"
if not exist "%PYTHON%" (
  echo Python not found. Edit path in this file.
  pause
  exit /b 1
)
"%PYTHON%" -m pip install boto3 requests Pillow "vastai==1.8.3" imageio-ffmpeg
if errorlevel 1 echo Installation failed. Check pip availability.
pause
