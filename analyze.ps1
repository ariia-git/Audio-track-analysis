. "$PSScriptRoot/bootstrap.ps1"
if (!(Test-Path -LiteralPath $LocalPython)) { Write-Error 'Run .\setup.ps1 first.'; exit 1 }
& $LocalPython -m src.main @args
exit $LASTEXITCODE
