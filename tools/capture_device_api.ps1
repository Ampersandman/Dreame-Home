param(
    [string]$Region = 'eu',
    [int]$Seconds = 180,
    [string]$OutputPath,
    [string]$StatusPath
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskCollector = Join-Path $PSScriptRoot 'capture_device_api.py'
$captureStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if (-not $OutputPath) { $OutputPath = Join-Path $taskRoot "private\api-$captureStamp.json" }
if (-not $StatusPath) { $StatusPath = Join-Path $taskRoot "private\api-$captureStamp.status.json" }
Set-Location -LiteralPath $taskRoot
& $taskPython $taskCollector --region $Region --seconds $Seconds --output $OutputPath --status $StatusPath
exit $LASTEXITCODE
