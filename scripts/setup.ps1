$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { python -m venv .venv }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& '.\.venv\Scripts\python.exe' -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw 'Project installation failed' }
npm.cmd ci --prefix web
if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed' }
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Web build failed' }
Write-Output 'Web build ready. Run scripts/start.ps1 and open the displayed localhost URL.'
