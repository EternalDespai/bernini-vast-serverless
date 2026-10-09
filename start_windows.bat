@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt || goto :fail
py run_local_ui.py || goto :fail
exit /b 0
:fail
echo.
echo Startup failed. Check the message above and your .env file.
pause
exit /b 1
