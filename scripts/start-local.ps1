param(
    [string]$HostName = "0.0.0.0",
    [int]$Port = 8000
)

$scriptPath = Join-Path $PSScriptRoot "dev-local.ps1"
& $scriptPath -HostName $HostName -Port $Port
