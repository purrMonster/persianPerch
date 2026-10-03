# run-kitten.ps1 - what the Scheduled Task runs on roastery: read kitten's settings, then run kitten.
# ASCII-only on purpose (PowerShell 5, test S8). Installed by install-kitten.ps1; not run by hand.
#
# The settings come from roastery's own .env.local (stacks\roastery\.env.local in the fleet clone), the file
# setup-secrets.ps1 fills: DOMAIN (already there) and KITTEN_TOKEN (asked for, see local.env.example). They are
# read here, at start, and placed in this process's environment only: the token is never in the task's definition,
# its arguments or a file of ours. kitten itself is the zipapp built from persianPerch (standard library only).
param(
    [Parameter(Mandatory = $true)][string]$FleetRoot,
    [Parameter(Mandatory = $true)][string]$Pyz,
    [Parameter(Mandatory = $true)][string]$Python,
    [string]$Log = 'C:\ProgramData\purrbrews\kitten\kitten.log'
)
$ErrorActionPreference = 'Stop'

function Write-Log([string]$text) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $text
    Add-Content -Path $Log -Value $line
}

# Keep the log small: when it passes 1 MB, the last 500 lines stay.
if ((Test-Path $Log) -and ((Get-Item $Log).Length -gt 1MB)) {
    $tail = Get-Content -Path $Log -Tail 500
    Set-Content -Path $Log -Value $tail
}

function Read-EnvFile([string]$path) {
    $values = @{}
    foreach ($line in Get-Content -Path $path) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $values[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
        }
    }
    return $values
}

$envFile = Join-Path $FleetRoot 'stacks\roastery\.env.local'
if (-not (Test-Path $envFile)) { Write-Log "stopped: $envFile not found (run setup-secrets.ps1 in stacks\roastery)"; exit 2 }
$s = Read-EnvFile $envFile
$domain = $s['DOMAIN']
$token = $s['KITTEN_TOKEN']
if (-not $domain -or $domain -like 'REPLACE_ME*') { Write-Log 'stopped: DOMAIN is not set in .env.local'; exit 2 }
if (-not $token -or $token -like 'REPLACE_ME*') { Write-Log 'stopped: KITTEN_TOKEN is not set in .env.local (run setup-secrets.ps1)'; exit 2 }

$env:KITTEN_PERCH_URL = "https://perch.$domain/api/kitten"
$env:KITTEN_TOKEN = $token
$env:KITTEN_NODE = 'roastery'
$env:KITTEN_STATE_DIR = ''
if ($s['KITTEN_POUNCE_PATHS']) { $env:KITTEN_POUNCE_PATHS = $s['KITTEN_POUNCE_PATHS'] }
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'

Write-Log "starting kitten ($Pyz) as roastery"
# PowerShell 5 turns a native program's stderr lines into errors; here they are just log lines.
$ErrorActionPreference = 'Continue'
& $Python $Pyz 2>&1 | ForEach-Object { Write-Log "$_" }
$code = $LASTEXITCODE
Write-Log "kitten stopped (exit $code); the task restarts it"
exit $code
