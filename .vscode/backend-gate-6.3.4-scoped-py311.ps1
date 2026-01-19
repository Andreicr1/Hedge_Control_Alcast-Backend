$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Py = Join-Path $RepoRoot ".venv311\Scripts\python.exe"

$ScopedFiles = @(
  "backend\app\api\router.py",
  "backend\app\api\routes\finance_pipeline_daily.py",
  "backend\app\schemas\finance_pipeline.py",
  "backend\app\schemas\__init__.py",
  "backend\tests\test_finance_pipeline_api.py"
)

& $Py -m ruff check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Py -m ruff format --check @ScopedFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location (Join-Path $RepoRoot "backend")
& $Py -m pytest -q "tests\test_finance_pipeline_api.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
