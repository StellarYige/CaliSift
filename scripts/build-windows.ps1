param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$pythonPath = (Resolve-Path -LiteralPath '.venv\Scripts\python.exe').Path
if (-not [Environment]::Is64BitOperatingSystem) { throw 'The Windows release requires x64.' }
& $pythonPath -X utf8 -m scripts.install_ocr
if ($LASTEXITCODE -ne 0) { throw 'Model verification failed.' }
if (-not $SkipTests) {
    $env:CALISIFT_REQUIRE_OCR = '1'
    & $pythonPath -X utf8 -m pytest --cov=xingcheng --cov-branch --cov-fail-under=90 --cov-report=term --cov-report=json:artifacts/coverage.json --junitxml=artifacts/pytest-results.xml
    if ($LASTEXITCODE -ne 0) { throw 'Python release checks failed.' }
    npm.cmd test --prefix desktop
    if ($LASTEXITCODE -ne 0) { throw 'Desktop tests failed.' }
    npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw 'Migration tests failed.' }
}
npm.cmd run build --prefix desktop
if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
& $pythonPath -X utf8 -m scripts.collect_licenses
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
& $pythonPath -X utf8 -m scripts.package_sources
if ($LASTEXITCODE -ne 0) { throw 'Corresponding source packaging failed.' }
& $pythonPath -X utf8 -m scripts.fetch_build_tools
if ($LASTEXITCODE -ne 0) { throw 'Toolchain download or checksum failed.' }
foreach ($filename in @('innosetup-6.7.3.exe','MicrosoftEdgeWebView2RuntimeInstallerX64.exe')) {
    $signature = Get-AuthenticodeSignature -LiteralPath (Join-Path 'artifacts\toolchain' $filename)
    if ($signature.Status -ne 'Valid') { throw "Invalid publisher signature: $filename" }
}
$compiler = Join-Path (Get-Location) 'artifacts\toolchain\inno\ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $installer = (Resolve-Path -LiteralPath 'artifacts\toolchain\innosetup-6.7.3.exe').Path
    $directory = Join-Path (Get-Location) 'artifacts\toolchain\inno'
    $arguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER',('/DIR="'+$directory+'"'))
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Inno Setup installation failed.' }
}
& $pythonPath -X utf8 -m PyInstaller --noconfirm packaging/calisift.spec
if ($LASTEXITCODE -ne 0) { throw 'Executable packaging failed.' }
& $compiler packaging/calisift.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
& $pythonPath -X utf8 -m scripts.package_models
if ($LASTEXITCODE -ne 0) { throw 'Model repair packaging failed.' }
& $pythonPath -X utf8 -m scripts.package_manifest
if ($LASTEXITCODE -ne 0) { throw 'Release checksum generation failed.' }
Write-Output 'Release assets are in artifacts/release. Run the native and installation smoke checks before publishing.'
