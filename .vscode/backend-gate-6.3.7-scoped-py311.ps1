$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Py = Join-Path $RepoRoot ".venv311\Scripts\python.exe"

$ScopedFiles = @(
  "backend\app\models\cashflow_baseline.py",
  "backend\app\models\finance_risk_flags.py",
  "backend\app\models\__init__.py",
  "backend\app\services\cashflow_baseline_service.py",
  "backend\app\services\finance_risk_flags_service.py",
  "backend\app\services\finance_pipeline_daily.py",
  "backend\alembic\versions\20260114_0004_add_cashflow_baseline_and_risk_flags.py",
  "backend\tests\test_finance_pipeline_cashflow_baseline_and_risk_flags.py"
)

& $Py -m ruff check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Py -m ruff format --check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location (Join-Path $RepoRoot "backend")
& $Py -m pytest -q "tests\test_finance_pipeline_cashflow_baseline_and_risk_flags.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
