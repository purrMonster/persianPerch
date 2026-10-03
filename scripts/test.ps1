# scripts/test.ps1 - persianPerch's whole test suite, in containers only (05 plan Q5, 3).
# ASCII-only on purpose (PowerShell 5, test S8). Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File scripts\test.ps1            # everything
#   powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -SkipUi    # without Playwright
# Exits non-zero if any step fails. Screenshots land in .\screenshots (gitignored).
param(
    [switch]$SkipUi,
    [switch]$Force   # run inside the 01:20-04:00 quiet hours anyway
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

# Images pinned by tag and digest (runbook, M0 entry). Bump tag and digest together.
$py312 = 'python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f'
$py313 = 'python:3.13-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b'
$py314 = 'python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d'
$fleetCommit = 'f94efdfb1995d7217ec2be33e45b33720a0a0b3b'
$fleetDir = Join-Path $root '.cache\purrbrews-containers'

# Container-safety rule (AGENTS.md 2.8): every container this script starts carries this label, and
# anything it cleans up is selected by it (or by the compose project), never "all containers".
$label = 'com.purrbrews.project=persianperch'

# In a git worktree, .git is a file that points at the main repo's .git by a host path
# the container can't see, so tests S5/S6/S8 (git ls-files) would fail with exit 128.
# Mount the main .git read-only and tell the tests where this worktree's own git directory
# is (PERCH_TEST_GIT_DIR, used only for this project's repo by tests/conftest.py).
$gitArgs = @()
$dotGit = Join-Path $root '.git'
if (Test-Path $dotGit -PathType Leaf) {
    $pointer = (Get-Content $dotGit -TotalCount 1)
    if ($pointer -match '^gitdir:\s*(.+)$') {
        $worktreeGitDir = $Matches[1].Trim().Replace('\', '/')
        $mainGitDir = Split-Path (Split-Path $worktreeGitDir)
        $gitArgs = @('-v', "${mainGitDir}:/gitmain:ro", '-e', "PERCH_TEST_GIT_DIR=/gitmain/worktrees/$(Split-Path $worktreeGitDir -Leaf)")
    }
}

# roastery holds the restic repository; cellar wakes it for the nightly backups.
$now = Get-Date
$minutes = $now.Hour * 60 + $now.Minute
if (-not $Force -and $minutes -ge 80 -and $minutes -lt 240) {
    Write-Host 'Quiet hours (01:20-04:00): no image builds or long test runs. Use -Force to override.'
    exit 2
}

$results = [ordered]@{}
function Step([string]$name, [scriptblock]$body) {
    Write-Host ''
    Write-Host "=== $name"
    $global:LASTEXITCODE = 0
    # Native tools write progress to stderr; PowerShell 5 would turn that into errors.
    # Judge each step by its exit code only.
    $ErrorActionPreference = 'Continue'
    try { & $body 2>&1 | ForEach-Object { $line = "$_"; if ($line -eq 'System.Management.Automation.RemoteException') { $line = '' }; Write-Host $line }; $code = $LASTEXITCODE } catch { Write-Host $_; $code = 1 }
    $ErrorActionPreference = 'Stop'
    if ($null -eq $code) { $code = 0 }
    $script:results[$name] = $code
    if ($code -ne 0) { Write-Host "--- $name FAILED (exit $code)" }
}

Step 'fleet repo pinned' {
    if (-not (Test-Path (Join-Path $fleetDir '.git'))) {
        # LF line endings, exactly as the nodes see the repo (runbook, M0 entry).
        git clone --quiet --config core.autocrlf=false https://github.com/purrMonster/purrbrews-containers $fleetDir
    }
    git -C $fleetDir -c advice.detachedHead=false checkout --quiet $fleetCommit
    $head = (git -C $fleetDir rev-parse HEAD).Trim()
    if ($head -ne $fleetCommit) { Write-Host "fleet repo at $head, expected $fleetCommit"; $global:LASTEXITCODE = 1 }
    else { Write-Host "fleet repo at $head" }
}

Step 'build test image' { docker build --quiet --label $label -f tests/Dockerfile -t persian-perch-test:dev . }

Step 'perch: ruff + pytest (3.12)' {
    docker run --rm --label $label @gitArgs -v "${root}:/src" -w /src persian-perch-test:dev sh -c 'ruff check . && pytest'
}

Step 'kitten: unittest (3.13)' {
    docker run --rm --label $label -v "${root}:/src" -w /src -e PYTHONDONTWRITEBYTECODE=1 $py313 python -m unittest discover -s tests/kitten
}

Step 'kitten: unittest (3.14)' {
    docker run --rm --label $label -v "${root}:/src" -w /src -e PYTHONDONTWRITEBYTECODE=1 $py314 python -m unittest discover -s tests/kitten
}

Step 'kitten: real inotifywait (3.13 + inotify-tools)' {
    docker build --quiet --label $label -f tests/kitten/Dockerfile -t persian-perch-kitten:inotify tests/kitten | Out-Null
    docker run --rm --label $label -v "${root}:/src" -w /src -e PYTHONDONTWRITEBYTECODE=1 -e KITTEN_REQUIRE_INOTIFY=1 persian-perch-kitten:inotify python -m unittest discover -s tests/kitten -p "test_pounce.py"
}

if (-not $SkipUi) {
    Step 'windowsill: Playwright UI check' {
        New-Item -ItemType Directory -Force -Path (Join-Path $root 'screenshots') | Out-Null
        docker compose -f tests/ui/compose.yml up --build --abort-on-container-exit --exit-code-from playwright
        $code = $LASTEXITCODE
        docker compose -f tests/ui/compose.yml down --volumes --remove-orphans | Out-Null
        $global:LASTEXITCODE = $code
    }
}

# The real-socket drill (05 plan 4 step 9): perch with every sense really running over loopback sockets against
# fakes of Komodo, ntfy, Gatus, Scrutiny and speedtest-tracker; memory budget; leak check. Exits non-zero on any failure.
Step 'real-socket drill: budget + leak check' {
    docker build --quiet --label $label -t persian-perch:ui-test . | Out-Null
    $mounts = @(
        '-v', "${root}\.cache\purrbrews-containers:/fleet:ro",
        '-v', "${root}\tests\ui\budget.py:/app/budget.py:ro",
        '-v', "${root}\tests\komodoFake.py:/app/komodoFake.py:ro",
        '-v', "${root}\tests\outsideFakes.py:/app/outsideFakes.py:ro",
        '-v', "${root}\tests\haFake.py:/app/haFake.py:ro"
    )
    docker run --rm --label $label -e PERCH_REPO_DIR=/fleet @mounts -w /app persian-perch:ui-test python budget.py
}

Write-Host ''
Write-Host '=== summary'
$failed = 0
foreach ($k in $results.Keys) {
    $mark = if ($results[$k] -eq 0) { 'ok  ' } else { $failed++; 'FAIL' }
    Write-Host ("{0} {1}" -f $mark, $k)
}
if ($failed -gt 0) { exit 1 }
exit 0
