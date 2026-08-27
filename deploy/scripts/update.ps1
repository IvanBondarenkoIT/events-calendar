param(
    [string]$DeployDir = "",
    [string]$Image = "ghcr.io/ivanbondarenkoit/events-calendar:latest"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DeployDir)) {
    $DeployDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

Write-Host "Pulling $Image ..."
docker pull $Image
Write-Host "Updated. Next scheduled run-slot will use the new image."
Write-Host "Optional smoke:"
Write-Host "  docker run --rm --env-file `"$DeployDir\.env`" -e PYTHONPATH=/app/src $Image python -m dec_calendar check-config"
