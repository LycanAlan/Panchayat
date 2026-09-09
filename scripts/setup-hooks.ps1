# Panchayat -- enable the shared git hooks. Run once, per machine.
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup-hooks.ps1
#
# Points git at .githooks/ instead of .git/hooks/, so the guard is version
# controlled and a fix reaches everyone on the next pull.

$ErrorActionPreference = "Stop"

$repo = git rev-parse --show-toplevel 2>$null
if (-not $repo) {
    Write-Host "Not inside a git repository." -ForegroundColor Red
    exit 1
}
Set-Location $repo

git config core.hooksPath .githooks

# Git for Windows runs hooks through its bundled sh, so the executable bit
# only matters for teammates on macOS or Linux. Set it anyway -- it travels
# in the index and saves them a step.
git update-index --chmod=+x .githooks/pre-commit 2>$null | Out-Null

$configured = git config core.hooksPath
if ($configured -eq ".githooks") {
    Write-Host ""
    Write-Host "  Hooks enabled." -ForegroundColor Green
    Write-Host ""
    Write-Host "  Commits to main are now blocked, and staged AWS keys or .env"
    Write-Host "  files are refused before they can reach the repo."
    Write-Host ""
    Write-Host "  Override when you genuinely mean to:  git commit --no-verify" -ForegroundColor DarkGray
    Write-Host ""
} else {
    Write-Host "Failed to set core.hooksPath (got '$configured')." -ForegroundColor Red
    exit 1
}
