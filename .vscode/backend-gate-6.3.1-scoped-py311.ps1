$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Py = Join-Path $RepoRoot ".venv311\Scripts\python.exe"

$ScopedFiles = @(
  "backend\app\models\domain.py",
  "backend\app\models\__init__.py",
  "backend\app\services\finance_pipeline_run_service.py",
  "backend\tests\test_finance_pipeline_runs.py"
)

& $Py -m ruff check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Py -m ruff format --check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location (Join-Path $RepoRoot "backend")
& $Py -m pytest -q "tests\test_finance_pipeline_runs.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
