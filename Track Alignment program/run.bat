@echo off
cd /d "%~dp0"
echo Current directory: %CD%
echo.
python --version
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Program exited with error code %ERRORLEVEL%.
    pause
)
