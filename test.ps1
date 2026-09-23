. "$PSScriptRoot/bootstrap.ps1"
if (!(Test-Path -LiteralPath $LocalPython)) { Write-Error 'Run .\setup.ps1 first.'; exit 1 }
Push-Location $ProjectRoot
try {
    & $LocalPython -m pytest tests -v -o 'cache_dir=runtime/cache/pytest' --basetemp=runtime/cache/test-temp @args
    $result = $LASTEXITCODE
} finally { Pop-Location }
exit $result
