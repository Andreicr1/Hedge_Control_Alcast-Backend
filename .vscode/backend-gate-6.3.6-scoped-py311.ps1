$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Py = Join-Path $RepoRoot ".venv311\Scripts\python.exe"

$ScopedFiles = @(
  "backend\app\models\mtm_contract_snapshot.py",
  "backend\app\models\__init__.py",
  "backend\app\services\mtm_contract_snapshot_service.py",
  "backend\app\services\mtm_contract_timeline.py",
  "backend\app\services\finance_pipeline_daily.py",
  "backend\alembic\versions\20260114_0003_add_mtm_contract_snapshots.py",
  "backend\tests\test_finance_pipeline_mtm_contract_integration.py"
)

& $Py -m ruff check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Py -m ruff format --check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location (Join-Path $RepoRoot "backend")
& $Py -m pytest -q "tests\test_finance_pipeline_mtm_contract_integration.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
