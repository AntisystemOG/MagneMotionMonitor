@echo off
REM Double-clickable manual build for MagneMotion Monitor.
REM Bumps the version, builds dist\MagneMotionMonitor.exe, then commits and
REM pushes to GitHub (skipped automatically if no git remote is set up yet).
REM Same as running "python release.py" — this just saves opening a terminal.

setlocal
cd /d "%~dp0"

echo ============================================================
echo   MagneMotion Monitor - Build ^& Release
echo ============================================================
echo.

python release.py
set BUILD_RESULT=%ERRORLEVEL%

echo.
if %BUILD_RESULT% EQU 0 (
    echo ============================================================
    echo   Done. See dist\MagneMotionMonitor.exe
    echo ============================================================
) else (
    echo ============================================================
    echo   Build failed - see the output above for details.
    echo ============================================================
)

pause
endlocal
exit /b %BUILD_RESULT%
