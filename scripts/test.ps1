$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& '.\.venv\Scripts\python.exe' -X utf8 -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm.cmd test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm.cmd run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm.cmd run test:browser
exit $LASTEXITCODE
