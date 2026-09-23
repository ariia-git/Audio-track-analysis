# Shared local environment; dot-sourced by entry points.
$ProjectRoot = $PSScriptRoot
$ErrorActionPreference = 'Stop'
foreach ($folder in @('runtime/cache/tmp','runtime/cache/pip','runtime/cache/numba','runtime/cache/matplotlib','runtime/cache/huggingface','logs','input','output')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot $folder) | Out-Null
}
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONUTF8 = '1'
$env:PIP_CONFIG_FILE = 'NUL'
$env:PIP_CACHE_DIR = Join-Path $ProjectRoot 'runtime/cache/pip'
$env:TEMP = Join-Path $ProjectRoot 'runtime/cache/tmp'
$env:TMP = $env:TEMP
$env:NUMBA_CACHE_DIR = Join-Path $ProjectRoot 'runtime/cache/numba'
$env:MPLCONFIGDIR = Join-Path $ProjectRoot 'runtime/cache/matplotlib'
$env:HF_HOME = Join-Path $ProjectRoot 'runtime/cache/huggingface'
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
$env:XDG_CACHE_HOME = Join-Path $ProjectRoot 'runtime/cache'
$LocalPython = Join-Path $ProjectRoot 'runtime/python/python.exe'
