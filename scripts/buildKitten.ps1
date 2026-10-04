# scripts/buildKitten.ps1 - build kitten's zipapp (dist\kitten.pyz) in a container, so nothing is installed on roastery.
# ASCII-only on purpose (PowerShell 5, test S8). Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File scripts\buildKitten.ps1
# The archive holds the standard library only and runs on the nodes' Python 3.13 and roastery's 3.14. It is a build
# output: dist\ is gitignored. Copy it to a node with integration\kitten (see integration\ROLLOUT.md).
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

# Same image, by tag and digest, as scripts\test.ps1's kitten step (Python 3.13, like the nodes).
$py313 = 'python:3.13-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b'
# Container-safety rule (AGENTS.md 2.8): the container this starts carries the project label.
$label = 'com.purrbrews.project=persianperch'

New-Item -ItemType Directory -Force -Path (Join-Path $root 'dist') | Out-Null
docker run --rm --label $label -v "${root}:/src" -w /src -e PYTHONDONTWRITEBYTECODE=1 $py313 python -m kitten.build dist/kitten.pyz
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$pyz = Join-Path $root 'dist\kitten.pyz'
$hash = (Get-FileHash -Algorithm SHA256 -Path $pyz).Hash.ToLower()
Write-Host "built $pyz"
Write-Host "sha256 $hash"
Write-Host 'Compare this hash on the node after copying (sha256sum kitten.pyz) before installing it.'
