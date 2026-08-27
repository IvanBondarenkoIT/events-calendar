param(
    [string]$DeployDir = "",
    [string]$MorningAt = "10:00",
    [string]$EveningAt = "22:00",
    [string]$RunAsUser = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DeployDir)) {
    $DeployDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    if (!(Test-Path (Join-Path $DeployDir "deploy\scripts\run-slot.ps1"))) {
        $DeployDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    }
}

$runner = Join-Path $DeployDir "deploy\scripts\run-slot.ps1"
if (!(Test-Path -LiteralPath $runner)) {
    # Server layout: C:\events-calendar\scripts\run-slot.ps1
    $runner = Join-Path $DeployDir "scripts\run-slot.ps1"
}
if (!(Test-Path -LiteralPath $runner)) {
    throw "Runner not found under $DeployDir"
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

function Install-DecTask {
    param([string]$Name, [string]$Slot, [string]$At)

    $psArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -Slot $Slot -DeployDir `"$DeployDir`""
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs -WorkingDirectory $DeployDir
    $trigger = New-ScheduledTaskTrigger -Daily -At $At

    if (![string]::IsNullOrWhiteSpace($RunAsUser)) {
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -User $RunAsUser -RunLevel Highest -Force | Out-Null
    }
    else {
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    }
    Write-Host "Installed '$Name' daily at $At (slot=$Slot)"
}

Install-DecTask -Name "DecCalendarMorning" -Slot "morning" -At $MorningAt
Install-DecTask -Name "DecCalendarEvening" -Slot "evening" -At $EveningAt

Write-Host "Host timezone should be Asia/Tbilisi (or adjust -MorningAt/-EveningAt)."
Write-Host "Logs: $DeployDir\logs\dec-SLOT-*.log"
Write-Host "Runner: $runner"
