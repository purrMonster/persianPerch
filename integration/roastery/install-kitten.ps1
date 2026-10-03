# install-kitten.ps1 - install persianPerch's kitten on roastery as a Scheduled Task (05 plan A5).
# ASCII-only on purpose (PowerShell 5, test S8). Run from an elevated PowerShell (Run as administrator):
#
#   .\install-kitten.ps1 -FleetRoot C:\path\to\purrbrews-containers              install (or update) and start
#   .\install-kitten.ps1 -FleetRoot C:\path\to\purrbrews-containers -DryRun      say what it would do, change nothing
#   .\install-kitten.ps1 -Remove                                                  stop and remove the task and its folder
#
# Before this: build dist\kitten.pyz (scripts\buildKitten.ps1 in the persianPerch repo) and run
# .\setup-secrets.ps1 in the fleet clone's stacks\roastery, which asks for KITTEN_TOKEN (the token cellar made for
# roastery) and stores it in roastery's own .env.local. This script never asks for, prints or stores the token.
#
# What it does, and nothing else:
#   1. copies kitten.pyz and run-kitten.ps1 to C:\ProgramData\purrbrews\kitten (not under C:\purrbrews: that folder is the
#      restic repository's chroot and its permissions belong to backup-target\setup.ps1);
#   2. registers the task "purrBrews kitten": starts at boot and when roastery wakes from sleep, runs as the user who
#      installs it (without storing a password, with the rights of an administrator, so it can list the snapshots
#      folder), restarts itself if it stops, and never starts a second copy;
#   3. starts it.
# kitten only reads and sends: no inbound port, no firewall rule, nothing written to the fleet. roastery sleeps; while
# it does, kitten is not running, and perch knows roastery's wake window (05 plan C5), so silence outside it is fine.
param(
    [string]$FleetRoot = '',
    [string]$Pyz = (Join-Path $PSScriptRoot '..\..\dist\kitten.pyz'),
    [string]$Python = '',
    [string]$InstallDir = 'C:\ProgramData\purrbrews\kitten',
    [switch]$DryRun,
    [switch]$Remove
)
$ErrorActionPreference = 'Stop'
$TaskName = 'purrBrews kitten'

function Say([string]$text) { Write-Host $text }
function Do-Step([string]$what, [scriptblock]$body) {
    if ($DryRun) { Say "  [dry run] $what" } else { Say "  $what"; & $body }
}

if (-not $DryRun) {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this from an elevated PowerShell (Run as administrator).'
    }
}

if ($Remove) {
    Say "Removing the task and $InstallDir"
    Do-Step "stop and unregister '$TaskName'" {
        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
    }
    Do-Step "delete $InstallDir (only the folder this script made)" {
        if ((Test-Path $InstallDir) -and ($InstallDir -like '*\purrbrews\kitten')) { Remove-Item -Recurse -Force $InstallDir }
    }
    exit 0
}

# --- checks -----------------------------------------------------------------------------------------------------
if (-not $FleetRoot) { throw 'Say where the purrbrews-containers clone is: -FleetRoot C:\path\to\purrbrews-containers' }
$envFile = Join-Path $FleetRoot 'stacks\roastery\.env.local'
if (-not (Test-Path $envFile)) { throw "${envFile} not found: run .\setup-secrets.ps1 in stacks\roastery first." }
$haveToken = $false
$haveDomain = $false
foreach ($line in Get-Content -Path $envFile) {
    if ($line -match '^\s*KITTEN_TOKEN=(.+)$' -and $Matches[1] -notlike 'REPLACE_ME*') { $haveToken = $true }
    if ($line -match '^\s*DOMAIN=(.+)$' -and $Matches[1] -notlike 'REPLACE_ME*') { $haveDomain = $true }
}
if (-not $haveDomain) { throw "DOMAIN is not set in ${envFile}." }
if (-not $haveToken) { throw "KITTEN_TOKEN is not set in ${envFile}: run .\setup-secrets.ps1 in stacks\roastery and paste the token cellar made for roastery." }
if (-not (Test-Path $Pyz)) { throw "kitten.pyz not found at ${Pyz}: run scripts\buildKitten.ps1 in the persianPerch repo." }
$Pyz = (Resolve-Path $Pyz).Path

if (-not $Python) {
    # roastery's own Python (3.14); the Microsoft Store alias in WindowsApps is not a Python.
    $found = Get-Command python.exe -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1
    if (-not $found) { throw 'No Python found on PATH. Pass -Python C:\path\to\python.exe (kitten needs 3.13 or newer).' }
    $Python = $found.Source
}
$version = (& $Python --version 2>&1 | Out-String).Trim()
if ($version -notmatch 'Python 3\.(\d+)' -or [int]$Matches[1] -lt 13) { throw "kitten needs Python 3.13 or newer; $Python is '$version'." }

Say "kitten on roastery"
Say "  python  : $Python ($version)"
Say "  kitten  : $Pyz"
Say "  settings: $envFile (read when the task starts; the token stays there)"
Say "  folder  : $InstallDir"

# --- install ----------------------------------------------------------------------------------------------------
Do-Step "create $InstallDir and copy kitten.pyz and run-kitten.ps1" {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Copy-Item -Force -Path $Pyz -Destination (Join-Path $InstallDir 'kitten.pyz')
    Copy-Item -Force -Path (Join-Path $PSScriptRoot 'run-kitten.ps1') -Destination (Join-Path $InstallDir 'run-kitten.ps1')
}

$runner = Join-Path $InstallDir 'run-kitten.ps1'
$installedPyz = Join-Path $InstallDir 'kitten.pyz'
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -FleetRoot `"$FleetRoot`" -Pyz `"$installedPyz`" -Python `"$Python`""

Do-Step "register the task '$TaskName' (at startup and on wake; restarts itself; one copy at a time)" {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
    $atBoot = New-ScheduledTaskTrigger -AtStartup
    # On wake: the Power-Troubleshooter event 1 means "the system has resumed from sleep".
    $eventClass = Get-CimClass -ClassName MSFT_TaskEventTrigger -Namespace Root/Microsoft/Windows/TaskScheduler
    $onWake = New-CimInstance -CimClass $eventClass -ClientOnly
    $onWake.Subscription = '<QueryList><Query Id="0" Path="System"><Select Path="System">*[System[Provider[@Name=''Microsoft-Windows-Power-Troubleshooter''] and EventID=1]]</Select></Query></QueryList>'
    $onWake.Enabled = $true
    $me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $who = New-ScheduledTaskPrincipal -UserId $me -LogonType S4U -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($atBoot, $onWake) -Principal $who -Settings $settings -Force `
        -Description "persianPerch kitten: tells perch on cellar that roastery is up (stacks, snapshots). Read-only." | Out-Null
}

Do-Step "start the task now" { Start-ScheduledTask -TaskName $TaskName }

Say ''
Say 'Check (ROLLOUT.md has the rest):'
Say "  Get-Content -Tail 20 $InstallDir\kitten.log     the last lines of what kitten said"
Say "  Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Say '  the perch overview shows roastery reporting while it is awake'
