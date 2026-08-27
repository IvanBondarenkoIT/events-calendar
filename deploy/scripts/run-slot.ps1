param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("morning", "evening")]
    [string]$Slot,

    [string]$DeployDir = "",
    [string]$Image = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DeployDir)) {
    # deploy/scripts -> repo root (local) or C:\events-calendar (server copy)
    $DeployDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    if (!(Test-Path (Join-Path $DeployDir "docker-compose.prod.yml"))) {
        $DeployDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    }
}

if ([string]::IsNullOrWhiteSpace($Image)) {
    $Image = $env:DEC_IMAGE
    if ([string]::IsNullOrWhiteSpace($Image)) {
        $Image = "ghcr.io/ivanbondarenkoit/events-calendar:latest"
    }
}

$envFile = Join-Path $DeployDir ".env"
$dataDir = Join-Path $DeployDir "data"
$logsDir = Join-Path $DeployDir "logs"

if (!(Test-Path -LiteralPath $envFile)) {
    throw ".env not found: $envFile"
}
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $logsDir "dec-$Slot-$stamp.log"

$dockerArgs = @(
    "run", "--rm",
    "--env-file", $envFile,
    "-e", "TZ=Asia/Tbilisi",
    "-e", "PYTHONPATH=/app/src",
    "-e", "IDEMPOTENCY_PATH=/app/data/alert_state.json",
    "-v", "${dataDir}:/app/data",
    $Image,
    "python", "-m", "dec_calendar", "run-once", "--slot", $Slot
)

Write-Host "DeployDir=$DeployDir"
Write-Host "Image=$Image Slot=$Slot"
Write-Host "Log=$logFile"

$exitCode = 0
try {
    & docker @dockerArgs 2>&1 | Tee-Object -FilePath $logFile
    $exitCode = $LASTEXITCODE
}
catch {
    $_ | Tee-Object -FilePath $logFile -Append
    $exitCode = 1
}

if ($exitCode -ne 0) {
    Write-Error "dec-calendar run-once --slot $Slot failed with exit code $exitCode (see $logFile)"
    exit $exitCode
}

Write-Host "OK slot=$Slot"
exit 0
