param(
    [string]$Region = 'eu',
    [string]$OutputPath,
    [string]$StatusPath
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskScanner = Join-Path $PSScriptRoot 'scan_cloud_account.py'
$scanStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if (-not $OutputPath) { $OutputPath = Join-Path $taskRoot "private\devices-$scanStamp.json" }
if (-not $StatusPath) { $StatusPath = Join-Path $taskRoot "private\scan-$scanStamp.status.json" }
Set-Location -LiteralPath $taskRoot
& $taskPython $taskScanner --region $Region --output $OutputPath --status $StatusPath
exit $LASTEXITCODE
