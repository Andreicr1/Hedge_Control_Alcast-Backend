$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Py = Join-Path $RepoRoot ".venv311\Scripts\python.exe"

$ScopedFiles = @(
  "backend\app\api\deps.py",
  "backend\app\api\routes\cashflow.py",
  "backend\app\schemas\cashflow_advanced.py",
  "backend\app\schemas\__init__.py",
  "backend\app\services\cashflow_advanced_service.py",
  "backend\tests\test_cashflow_advanced_preview.py"
)

& $Py -m ruff check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Py -m ruff format --check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location (Join-Path $RepoRoot "backend")
& $Py -m pytest -q "tests\test_cashflow_advanced_preview.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
