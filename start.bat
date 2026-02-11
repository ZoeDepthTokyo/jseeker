@echo off
REM jSeeker Launch Script - Clean start with cache clearing and port cleanup
echo ========================================
echo jSeeker Launch Script
echo ========================================
echo.

REM Change to jSeeker directory
cd /d "%~dp0"

echo [1/4] Clearing Python cache...
for /d /r . %%d in (__pycache__) do @if exist "%%d" (
    rd /s /q "%%d" 2>nul
)
echo       Done!

echo [2/4] Checking port 8502...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8502" ^| find "LISTENING"') do (
    echo       Killing process %%a on port 8502...
    taskkill /F /PID %%a >nul 2>&1
)
echo       Port 8502 is free!

echo [3/4] Activating virtual environment...
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate
    echo       Virtual environment activated!
) else (
    echo       WARNING: No virtual environment found at .venv\
    echo       Continuing with system Python...
)

echo [4/4] Launching jSeeker...
echo.
echo ========================================
echo Opening http://localhost:8502
echo Press CTRL+C to stop the server
echo ========================================
echo.

python run.py
