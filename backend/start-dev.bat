@echo off
setlocal
REM Start Backend Development Server (Windows)

echo ================================
echo Starting Backend Server
echo ================================
echo.

REM Always run from this script's directory so relative paths (e.g. .env, sqlite:///./*) are stable.
pushd "%~dp0"

REM Pick the most appropriate Python interpreter.
set "PY_EXE="
if exist ".venv311\Scripts\python.exe" set "PY_EXE=%CD%\.venv311\Scripts\python.exe"
if not defined PY_EXE if exist ".venv\Scripts\python.exe" set "PY_EXE=%CD%\.venv\Scripts\python.exe"

REM Activate virtual environment (optional but keeps parity with local dev).
if exist ".venv311\Scripts\activate.bat" call ".venv311\Scripts\activate.bat"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

if not defined PY_EXE (
    echo ERROR: Virtual environment not found!
    echo Please run setup-dev.bat first ^(creates .venv^) or ensure .venv311 exists.
    popd
    pause
    exit /b 1
)

REM Validate interpreter version (supported Python: 3.11.x)
for /f "tokens=2" %%v in ('"%PY_EXE%" -V 2^>^&1') do set PYVER=%%v
echo Using Python %PYVER%
echo %PYVER% | findstr /b "3.11." >nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo WARNING: This project supports Python 3.11.x.
    echo If you see import/type errors, recreate the venv using:
    echo   py -3.11 -m venv .venv
    echo.
)

REM Ensure DB schema is up-to-date (dev ergonomics)
echo.
echo Running migrations (alembic upgrade head)...
"%PY_EXE%" -m alembic upgrade head
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to run migrations.
    echo If this is a fresh setup, run: setup-dev.bat
    echo If you have an old dev.db, you may need to recreate it.
    popd
    pause
    exit /b 1
)

REM Start server
set "HOST=127.0.0.1"
if not "%UVICORN_HOST%"=="" set "HOST=%UVICORN_HOST%"

set "PORT=8001"
if not "%UVICORN_PORT%"=="" set "PORT=%UVICORN_PORT%"

echo Starting uvicorn server on port %PORT%...
echo.
echo Backend: http://%HOST%:%PORT%
echo API Docs: http://%HOST%:%PORT%/docs
echo.

"%PY_EXE%" -m uvicorn app.main:app --reload --host %HOST% --port %PORT% --app-dir "%CD%" --env-file "%CD%\.env"

popd
