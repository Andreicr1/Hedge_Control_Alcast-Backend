@echo off
setlocal
REM Setup Backend Development Environment (Windows)

echo ================================
echo Backend Development Setup
echo ================================
echo.

REM Always run from this script's directory so relative paths (e.g. .env, sqlite:///./*) are stable.
pushd "%~dp0"

REM Ensure Python 3.11 is available (policy: supported Python 3.11.x)
echo Checking for Python 3.11...
py -3.11 -c "import sys; print(f'Using Python {sys.version.split()[0]}')" 1>nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python 3.11 is required but was not found.
    echo Install Python 3.11.x and ensure the Python Launcher (py.exe) is available.
    echo.
    echo Example:
    echo   py -3.11 -V
    pause
    exit /b 1
)

REM Create virtual environment
echo [1/5] Creating virtual environment...
py -3.11 -m venv .venv
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

REM Activate virtual environment
echo [2/5] Activating virtual environment...
call .venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)

REM Install dependencies
echo [3/5] Installing dependencies...
python -m pip install -r requirements-dev.txt
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

REM Run migrations
echo [4/5] Running database migrations...
alembic upgrade head
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to run migrations
    pause
    exit /b 1
)

REM Seed users
echo [5/5] Seeding users...
python -m app.scripts.seed_users
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to seed users
    pause
    exit /b 1
)

echo.
echo ================================
echo Setup completed successfully!
echo ================================
echo.
echo To start the backend server:
echo   start-dev.bat
echo.
echo Defaults:
echo   Host: 127.0.0.1
echo   Port: 8001
echo.
echo Overrides (optional):
echo   set UVICORN_PORT=8000
echo   set UVICORN_HOST=0.0.0.0
echo   start-dev.bat
echo.
popd
pause
