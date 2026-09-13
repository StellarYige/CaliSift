$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
python scripts/serve-web.py
exit $LASTEXITCODE
