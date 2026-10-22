# Push this handover package to a GitHub repository under a subfolder.
#
# Usage (from this folder):
#   pwsh -File .\push_to_github.ps1
#   powershell -ExecutionPolicy Bypass -File .\push_to_github.ps1
#
# The first run will ask for GitHub credentials (browser or token).
# Nothing secret is copied: .env / venv / __pycache__ are excluded.

param(
    [string]$Repo   = 'https://github.com/chenzhaoho/czh',
    [string]$Subdir = 'EDA_Agent_LangGraph',
    [string]$Branch = 'main',
    [string]$Message = 'Update EDA Agent handover package'
)

$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot
$work = Join-Path $env:TEMP ('czh_push_' + [guid]::NewGuid().ToString('N').Substring(0, 6))

Write-Host "== Clone $Repo" -ForegroundColor Cyan
git clone $Repo $work
if (-not (Test-Path (Join-Path $work '.git'))) { throw 'git clone failed' }

$dest = Join-Path $work $Subdir
if (Test-Path $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
New-Item -ItemType Directory -Path $dest | Out-Null

Write-Host "== Copy package files" -ForegroundColor Cyan
$exclude = @('.git', 'venv', '.venv', '__pycache__', '.env')
Get-ChildItem -LiteralPath $src -Force | Where-Object { $exclude -notcontains $_.Name } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force
}

$name = (git config --global user.name) 2>$null
if (-not $name) { git -C $work config user.name 'chenzhaoho' }
$mail = (git config --global user.email) 2>$null
if (-not $mail) { git -C $work config user.email 'chenzhaoho@users.noreply.github.com' }

Write-Host "== Commit" -ForegroundColor Cyan
git -C $work add $Subdir
$changes = git -C $work status --porcelain
if (-not $changes) {
    Write-Host 'No changes to commit.' -ForegroundColor Yellow
    exit 0
}
git -C $work commit -m $Message

Write-Host "== Push (a credential window may appear)" -ForegroundColor Cyan
git -C $work push origin $Branch

Write-Host ""
Write-Host "Done. View at: https://github.com/chenzhaoho/czh/tree/$Branch/$Subdir" -ForegroundColor Green
Write-Host "Local clone kept at: $work"
