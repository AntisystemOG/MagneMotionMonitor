@echo off
REM Double-clickable manual build for MagneMotion Monitor.
REM Bumps the version, builds dist\MagneMotionMonitor.exe, then optionally
REM commits and pushes to GitHub (skipped automatically if no git remote is
REM set up yet).
REM
REM Same as running "python release.py" - this just saves opening a terminal.
REM Pass --push on the command line to build AND push.
REM Pass --fast to reuse the previous PyInstaller cache (much faster).

setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   MagneMotion Monitor - Build and Release
echo ============================================================
echo.

REM Default: build only (no git push). Use --push to also commit/push.
if /I "%~1"=="--push" (
    set "PUSH_ARG="
) else if /I "%~2"=="--push" (
    set "PUSH_ARG="
) else (
    set "PUSH_ARG=--no-push"
)

REM Default: clean build. Use --fast to reuse PyInstaller cache.
if /I "%~1"=="--fast" (
    set "FAST_ARG=--fast"
) else if /I "%~2"=="--fast" (
    set "FAST_ARG=--fast"
) else (
    set "FAST_ARG="
)

echo [1/2] Verifying track_photo.py / waypoints before build...
echo.
python scripts\verify_track_photo.py
set VERIFY_RESULT=%ERRORLEVEL%
if %VERIFY_RESULT% NEQ 0 (
    echo.
    echo ============================================================
    echo   Verification failed - fix track_photo.py / waypoints first.
    echo ============================================================
    pause
    endlocal
    exit /b %VERIFY_RESULT%
)

echo.
echo [2/2] Running: python release.py %PUSH_ARG% %FAST_ARG%
echo.

python release.py %PUSH_ARG% %FAST_ARG%
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
