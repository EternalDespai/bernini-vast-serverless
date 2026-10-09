@echo off
cd /d "%~dp0"
set "PYTHON=C:\AI\ComfyUI_windows_portable\python_embeded\python.exe"
if not exist "%PYTHON%" (
  echo Portable Python not found: %PYTHON%
  echo Edit START_WINDOWS.bat to set your Python path.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8765/"
"%PYTHON%" app.py
pause
