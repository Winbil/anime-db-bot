$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 "$Root\scripts\project.py" start @args
    exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python "$Root\scripts\project.py" start @args
    exit $LASTEXITCODE
}

Write-Error "Python 3.11-3.14 is required. Install Python and ensure 'py' or 'python' is on PATH."
exit 1
