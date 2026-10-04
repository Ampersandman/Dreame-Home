param([string]$Region = 'eu')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskFetcher = Join-Path $PSScriptRoot 'fetch_device_plugins.py'
Set-Location -LiteralPath $taskRoot
& $taskPython $taskFetcher --region $Region
exit $LASTEXITCODE
