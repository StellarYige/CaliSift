param([string]$BindAddress = '127.0.0.1', [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw '请先运行 .\scripts\setup.ps1' }
& '.\.venv\Scripts\python.exe' -m uvicorn xingcheng.api:app --host $BindAddress --port $Port
exit $LASTEXITCODE
