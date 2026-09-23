[CmdletBinding()]
param([switch]$WithWhisper)
. "$PSScriptRoot/bootstrap.ps1"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'
function Download([string]$Url, [string]$Destination) {
    if (!(Test-Path -LiteralPath $Destination)) {
        Write-Host "Downloading $Url"
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile "$Destination.partial"
        Move-Item -LiteralPath "$Destination.partial" -Destination $Destination -Force
    }
}
try {
    $downloads = Join-Path $ProjectRoot 'runtime/cache/downloads'
    New-Item -ItemType Directory -Force -Path $downloads | Out-Null
    if (!(Test-Path -LiteralPath $LocalPython)) {
        $archive = Join-Path $downloads 'python-3.12.10-embed-amd64.zip'
        Download 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' $archive
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $ProjectRoot 'runtime/python') -Force
    }
    # Embedded Python isolates imports. Explicitly opt into local site-packages and project root.
    @('python312.zip','.','Lib/site-packages','../../','import site') | Set-Content -Encoding ASCII -LiteralPath (Join-Path $ProjectRoot 'runtime/python/python312._pth')
    if (!(Test-Path -LiteralPath (Join-Path $ProjectRoot 'runtime/python/Lib/site-packages/pip'))) {
        $getPip = Join-Path $downloads 'get-pip.py'
        Download 'https://bootstrap.pypa.io/get-pip.py' $getPip
        & $LocalPython $getPip --no-warn-script-location
        if ($LASTEXITCODE -ne 0) { throw 'Local pip bootstrap failed.' }
    }
    & $LocalPython -m pip install --disable-pip-version-check --no-warn-script-location --only-binary=:all: -r (Join-Path $ProjectRoot 'requirements.txt') -c (Join-Path $ProjectRoot 'requirements-lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Core dependency installation failed.' }
    if ($WithWhisper) {
        & $LocalPython -m pip install --disable-pip-version-check --no-warn-script-location --only-binary=:all: -r (Join-Path $ProjectRoot 'requirements-whisper.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Optional Whisper installation failed.' }
    }
    $ffmpeg = Join-Path $ProjectRoot 'runtime/ffmpeg/bin/ffmpeg.exe'
    if (!(Test-Path -LiteralPath $ffmpeg)) {
        $archive = Join-Path $downloads 'ffmpeg-release-essentials.zip'
        Download 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' $archive
        $hashFile = "$archive.sha256"
        Download 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256' $hashFile
        $expected = ((Get-Content -LiteralPath $hashFile -Raw).Trim() -split '\s+')[0]
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) { throw 'FFmpeg checksum mismatch. Remove the cached FFmpeg ZIP and checksum, then rerun setup.' }
        $unpack = Join-Path $downloads 'ffmpeg-unpacked'
        Expand-Archive -LiteralPath $archive -DestinationPath $unpack -Force
        $build = Get-ChildItem -LiteralPath $unpack -Directory | Select-Object -First 1
        New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot 'runtime/ffmpeg') | Out-Null
        Copy-Item -Path (Join-Path $build.FullName '*') -Destination (Join-Path $ProjectRoot 'runtime/ffmpeg') -Recurse -Force
    }
    & $ffmpeg -version | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) { throw 'FFmpeg verification failed.' }
    Push-Location $ProjectRoot
    try {
        # Use a module instead of inline Python: Windows PowerShell 5.1 strips
        # embedded double quotes when passing native command arguments.
        & $LocalPython -m src.verify_runtime
        if ($LASTEXITCODE -ne 0) { throw 'Import verification failed.' }
        & $LocalPython -m pytest tests -q -m 'not integration' -o "cache_dir=runtime/cache/pytest"
        if ($LASTEXITCODE -ne 0) { throw 'Self-test failed.' }
    } finally { Pop-Location }
    Write-Host 'Setup complete. Run: .\analyze.ps1 "input\mix.mp3"'
} catch { Write-Error $_; exit 1 }
