$ErrorActionPreference = 'Stop'

$python = Join-Path $PSScriptRoot "..\..\.venv311\Scripts\python.exe"
if (-not (Test-Path $python)) {
	$python = "python"
}

Push-Location (Join-Path $PSScriptRoot "..")
try {
	$targets = @(
		"app\\api\\routes\\workflows.py",
		"app\\api\\routes\\rfqs.py",
		"app\\api\\routes\\hedge_manual.py",
		"app\\api\\router.py",
		"app\\schemas\\workflows.py",
		"app\\schemas\\rfq.py",
		"app\\schemas\\rfqs.py",
		"app\\schemas\\hedge_manual.py",
		"app\\services\\workflow_approvals.py",
		"tests\\test_kyc_gating.py"
	)

	& $python -m ruff check @targets
	& $python -m pytest -q "tests\\test_kyc_gating.py"
}
finally {
	Pop-Location
}
