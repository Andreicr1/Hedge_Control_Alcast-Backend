$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Py = Join-Path $RepoRoot ".venv311\Scripts\python.exe"

$ScopedFiles = @(
  "backend\app\models\domain.py",
  "backend\app\services\finance_pipeline_daily.py",
  "backend\alembic\versions\20260114_0002_add_finance_pipeline_step_artifacts.py",
  "backend\tests\test_finance_pipeline_pnl_integration.py"
)

& $Py -m ruff check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Py -m ruff format --check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location (Join-Path $RepoRoot "backend")
& $Py -m pytest -q "tests\test_finance_pipeline_pnl_integration.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
