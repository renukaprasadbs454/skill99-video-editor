@echo off
setlocal

echo ============================================
echo   Batch Video Processor
echo ============================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    where python3 >nul 2>nul
    if %errorlevel% neq 0 (
        echo ERROR: Python was not found on your PATH.
        echo Please install Python from https://www.python.org/downloads/
        echo During installation, make sure to check "Add Python to PATH".
        echo.
        pause
        exit /b 1
    ) else (
        python3 process_videos.py
        goto :end
    )
)

python process_videos.py

:end
echo.
echo ============================================
echo   Done. Press any key to close this window.
echo ============================================
pause >nul
