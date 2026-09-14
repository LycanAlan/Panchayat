# Redeploy the MAIN runtime (the request path, `panchayat`) from the working
# tree. The desks have scripts/deploy_desk.ps1; this is the same shape for the
# one agent that was, until 14 Sep, redeployed by hand and therefore not at
# all -- version 10 sat on a 13 Sep tree while three PRs landed on main.
#
# `agentcore launch` REPLACES the runtime's environment with what is passed,
# so every variable the runtime needs is passed every time. The set below is
# the one read back from the live runtime with get-agent-runtime on 14 Sep;
# core/clock.py refuses to schedule with an empty WATCHDOG_LAMBDA_ARN or
# SCHEDULER_ROLE_ARN, deliberately, so a missing one is loud rather than
# silent. GEMINI_API_KEY is read from .env and never written anywhere in the
# repo; it does reach the agentcore child process's argument list, which is
# the same exposure deploy_desk.ps1 has and is documented there.
#
#   .\scripts\deploy_runtime.ps1
#
[CmdletBinding()]
param(
    [string]$Agent = 'panchayat',
    [string]$Region = 'ap-south-2',
    [string]$AwsProfile = 'panchayat',
    [string]$Table = 'panchayat',
    [string]$WatchdogArn = 'arn:aws:lambda:ap-south-2:699073937307:function:panchayat-watchdog',
    [string]$SchedulerRoleArn = 'arn:aws:iam::699073937307:role/panchayat-scheduler'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:AWS_PROFILE = $AwsProfile
$env:PATH = (Join-Path $root '.venv\Scripts') + ';' + (Join-Path $root 'scripts') + ';' + $env:PATH
if (-not (Get-Command zip -ErrorAction SilentlyContinue)) {
    throw 'No zip on PATH even after adding scripts/. See scripts/zip_shim.py.'
}
$env:AGENTCORE_SUPPRESS_RECOMMENDATION = '1'

$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) { throw '.env not found; the runtime needs GEMINI_API_KEY.' }
$line = Get-Content $envFile | Where-Object { $_ -match '^\s*GEMINI_API_KEY\s*=' } | Select-Object -First 1
if (-not $line) { throw 'GEMINI_API_KEY is not set in .env.' }
$geminiKey = ($line -replace '^\s*GEMINI_API_KEY\s*=\s*', '').Trim().Trim('"').Trim("'")
if (-not $geminiKey) { throw 'GEMINI_API_KEY in .env is empty.' }

$configPath = Join-Path $root '.bedrock_agentcore.yaml'
if (-not (Select-String -Path $configPath -Pattern "^\s*$Agent\s*:\s*$" -Quiet)) {
    throw "No '$Agent' agent in .bedrock_agentcore.yaml; run agentcore configure first (docs/deploy/SETUP.md, stage 1)."
}

Write-Host "=== $Agent ($Region) ===" -ForegroundColor Cyan
& agentcore launch --agent $Agent `
    -env "PANCHAYAT_BACKEND=dynamodb" `
    -env "PANCHAYAT_TABLE=$Table" `
    -env "PANCHAYAT_MODEL=gemini" `
    -env "GEMINI_API_KEY=$geminiKey" `
    -env "TIME_SCALE=1" `
    -env "WATCHDOG_LAMBDA_ARN=$WatchdogArn" `
    -env "SCHEDULER_ROLE_ARN=$SchedulerRoleArn"
if ($LASTEXITCODE -ne 0) { throw "launch failed for $Agent (exit $LASTEXITCODE)" }

$ver = aws bedrock-agentcore-control list-agent-runtimes --region $Region --profile $AwsProfile `
    --query "agentRuntimes[?agentRuntimeName=='$Agent'].[agentRuntimeVersion,status]" --output text
if ($LASTEXITCODE -ne 0) { throw "list-agent-runtimes failed (exit $LASTEXITCODE)" }
Write-Host "$Agent -> version/status: $ver" -ForegroundColor Green
