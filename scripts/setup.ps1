$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspacePath
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '创建 Python 虚拟环境失败' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw '安装 Python 依赖失败' }
& '.\.venv\Scripts\python.exe' -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw '安装星程失败' }
& '.\.venv\Scripts\python.exe' -m scripts.install_ocr
if ($LASTEXITCODE -ne 0) { Write-Warning 'OCR 模型安装失败，Excel/CSV 仍可使用。稍后运行 python -m scripts.install_ocr 重试。' }
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw '安装前端测试依赖失败' }
npm.cmd ci --prefix desktop
if ($LASTEXITCODE -ne 0) { throw '安装桌面前端依赖失败' }
npm.cmd run build --prefix desktop
if ($LASTEXITCODE -ne 0) { throw '桌面界面构建失败' }
Write-Output 'CaliSift 准备完成。运行 .\scripts\start.ps1 打开桌面。可选 API 使用 .\scripts\start-api.ps1。'
