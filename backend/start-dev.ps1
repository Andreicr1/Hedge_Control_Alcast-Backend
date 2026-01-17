# Setup and Start Backend Development Server
# This script ensures the database is up to date and starts the backend

$ErrorActionPreference = "Stop"

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Backend Development Server" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Change to backend directory
Set-Location "c:\Projetos\Hedge_Control_Alcast-Backend\backend"

# Kill any existing uvicorn on port 8001
$port = 8001
$portCheck = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($portCheck) {
    Write-Host "Port $port is in use. Killing process..." -ForegroundColor Yellow
    $pids = $portCheck | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $pids) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

# Python executable
$python = "C:\Projetos\Hedge_Control_Alcast-Backend\.venv311\Scripts\python.exe"

# Ensure database tables exist
Write-Host "Checking database..." -ForegroundColor Yellow
& $python -c "from app.database import engine, Base; from app import models; Base.metadata.create_all(bind=engine); print('Database OK')"

# Check if users exist, seed if not
Write-Host "Checking users..." -ForegroundColor Yellow
$userCount = & $python -c "from app.database import SessionLocal; from app import models; db = SessionLocal(); print(db.query(models.User).count())"
if ($userCount -eq "0") {
    Write-Host "Seeding users..." -ForegroundColor Yellow
    & $python app/scripts/seed_users.py
} else {
    Write-Host "Users exist: $userCount" -ForegroundColor Green
}

# Start the server
Write-Host ""
Write-Host "Starting uvicorn on port $port..." -ForegroundColor Green
Write-Host "API Docs: http://localhost:$port/docs" -ForegroundColor Cyan
Write-Host ""

& $python -m uvicorn app.main:app --port $port --reload
