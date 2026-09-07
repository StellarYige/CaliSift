$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:CALISIFT_REQUIRE_OCR = '1'
& '.\.venv\Scripts\python.exe' -X utf8 -m pytest --cov=xingcheng --cov-branch --cov-report=term-missing --cov-fail-under=90
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
node --test tests-js/*.test.js
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm.cmd test --prefix desktop
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm.cmd run build --prefix desktop
exit $LASTEXITCODE
