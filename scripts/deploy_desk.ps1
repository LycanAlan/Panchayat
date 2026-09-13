# Deploy one simulated institution desk to AgentCore Runtime as an A2A server.
#
#   pwsh scripts/deploy_desk.ps1 -Desk ward
#   pwsh scripts/deploy_desk.ps1 -Desk ward,school,vendor,payments
#
# One runtime per desk, picked by PANCHAYAT_DESK. Five desks are five processes
# with five sets of state, exactly as on the laptop -- that separation is the
# trust boundary (CLAUDE.md), and collapsing it to save a deploy would make the
# A2A hop decorative.
#
# WHY A SCRIPT AND NOT TWO TYPED COMMANDS. Five traps, each of which cost us
# time on the first desk and each of which is closed here:
#
#   1. The entrypoint must sit at the REPO ROOT (desk_app.py). Configured as
#      institutions/a2a_runtime.py the toolkit records a Windows backslash and
#      the endpoint fails with "entrypoint could not be found in your artifact"
#      -- AFTER creating the runtime, so you are left deleting a broken one.
#   2. Agent names take no hyphens. panchayat_desk_<desk>, underscored.
#   3. A desk gets its OWN execution role. The main runtime's role can read our
#      case table; a desk that could do that is not a trust boundary.
#   4. agentcore uses the default credential chain, so AWS_PROFILE must be set
#      or it reports "No AWS credentials found" with valid keys on disk.
#   5. On Windows, `uv.exe` (.venv/Scripts) and our `zip` shim (scripts/) must
#      both be on PATH. The toolkit refuses direct_code_deploy with "zip utility
#      not found" -- a spurious shutil.which check for a binary it never runs,
#      see scripts/zip_shim.py -- and stock Windows has no zip.
#
# THE GEMINI KEY, STATED ACCURATELY. It is read from .env at run time and is
# never echoed to the console or written to a repo file. It IS passed to
# `agentcore launch` as an -env argument, which means it lands in that child
# process's argument vector: readable locally via Get-CimInstance Win32_Process
# or Task Manager's "Command line" column, and captured by PowerShell
# script-block logging (event 4104) or an active Start-Transcript.
#
# So this is protection against committing the key, not against a local
# observer. An earlier version of this comment claimed the key "never reaches a
# command line", which was false, and a false guarantee is worse than none --
# it is exactly the reason nobody thinks to rotate.
#
# Owner: Ali (platform).
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string[]]$Desk,
    [string]$Region = 'ap-south-2',
    [string]$AwsProfile = 'panchayat',
    [string]$ExecutionRole = 'arn:aws:iam::699073937307:role/panchayat-desk-exec',
    [string]$SourceBucket = 'bedrock-agentcore-codebuild-sources-699073937307-ap-south-2',
    [string]$DeskTable = 'panchayat-desks',
    [string]$OurTable = 'panchayat'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path (Join-Path $root 'desk_app.py'))) {
    throw 'desk_app.py is missing from the repo root. See trap 1 in the header.'
}

# Trap 4.
$env:AWS_PROFILE = $AwsProfile

# Trap 5. Prepended, so the venv's uv and our zip shim win over anything else.
$env:PATH = (Join-Path $root '.venv\Scripts') + ';' + (Join-Path $root 'scripts') + ';' + $env:PATH
if (-not (Get-Command zip -ErrorAction SilentlyContinue)) {
    throw 'No zip on PATH even after adding scripts/. See scripts/zip_shim.py.'
}

# The starter toolkit prints a six-line deprecation banner on every command,
# which buries the one line that matters when a deploy fails.
$env:AGENTCORE_SUPPRESS_RECOMMENDATION = '1'

# Read the key from .env rather than taking it as a parameter, so it is never
# typed, never in shell history, and never committed. See the header for what
# this does and does not protect against.
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) { throw '.env not found; the desks need GEMINI_API_KEY.' }
$line = Get-Content $envFile | Where-Object { $_ -match '^\s*GEMINI_API_KEY\s*=' } | Select-Object -First 1
if (-not $line) { throw 'GEMINI_API_KEY is not set in .env.' }
$geminiKey = ($line -replace '^\s*GEMINI_API_KEY\s*=\s*', '').Trim().Trim('"').Trim("'")
if (-not $geminiKey) { throw 'GEMINI_API_KEY in .env is empty.' }

if ($DeskTable -eq $OurTable) {
    throw "The desks may not share our table. See institutions/desk_store.py."
}

$known = @('bwssb', 'ward', 'school', 'vendor', 'payments')
$arns = @{}

# The sixth trap, which this script used to OPEN rather than close.
# `agentcore configure` rewrites `default_agent` in the shared
# .bedrock_agentcore.yaml, so after deploying desks the next `agentcore launch`
# or `agentcore invoke` typed WITHOUT --agent silently targets the last desk
# instead of the main `panchayat` runtime -- deploying a desk over the app.
# That file is gitignored, so the damage is invisible to review. Remember it
# here and put it back at the end.
$configPath = Join-Path $root '.bedrock_agentcore.yaml'
$defaultAgent = $null
if (Test-Path $configPath) {
    $hit = Select-String -Path $configPath -Pattern '^default_agent:\s*(.+)$' |
        Select-Object -First 1
    if ($hit) { $defaultAgent = $hit.Matches[0].Groups[1].Value.Trim() }
}

# Called as `powershell -File ... -Desk a,b,c` the whole list arrives as ONE
# string -- -File does not parse PowerShell array syntax, unlike -Command and
# unlike calling the script from a live prompt. Split here so both spellings
# work rather than failing on a difference in how the script was invoked.
$desks = $Desk | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim().ToLower() } |
    Where-Object { $_ }

foreach ($d in $desks) {
    if ($known -notcontains $d) { throw "Unknown desk '$d'. One of: $($known -join ', ')." }

    $name = "panchayat_desk_$d"     # trap 2: no hyphens
    Write-Host ''
    Write-Host "=== $name ===" -ForegroundColor Cyan

    & agentcore configure -n $name -e desk_app.py -p A2A -r $Region `
        -dt direct_code_deploy -rt PYTHON_3_12 -rf requirements-prod.txt `
        -ni -do -dm -er $ExecutionRole -s3 $SourceBucket
    if ($LASTEXITCODE -ne 0) { throw "configure failed for $name (exit $LASTEXITCODE)" }

    & agentcore launch --agent $name `
        -env "PANCHAYAT_DESK=$d" `
        -env 'PANCHAYAT_MODEL=gemini' `
        -env "GEMINI_API_KEY=$geminiKey" `
        -env "PANCHAYAT_DESK_TABLE=$DeskTable" `
        -env "PANCHAYAT_TABLE=$OurTable"
    if ($LASTEXITCODE -ne 0) { throw "launch failed for $name (exit $LASTEXITCODE)" }

    # Checked like the two calls above it. Without the exit-code test a failed
    # CLI call (expired token, throttling, wrong region) returns nothing, and
    # $null.Trim() throws "You cannot call a method on a null-valued
    # expression" -- pointing at PowerShell rather than at credentials, AFTER
    # the runtime has already been created.
    $arn = aws bedrock-agentcore-control list-agent-runtimes --region $Region `
            --profile $AwsProfile `
            --query "agentRuntimes[?agentRuntimeName=='$name'].agentRuntimeArn" `
            --output text
    if ($LASTEXITCODE -ne 0) { throw "list-agent-runtimes failed for $name (exit $LASTEXITCODE)" }
    if (-not $arn) { throw "$name did not appear in list-agent-runtimes." }
    $arn = $arn.Trim()
    $arns[$d] = $arn
    Write-Host "$name -> $arn" -ForegroundColor Green
}

if ($defaultAgent -and (Test-Path $configPath)) {
    (Get-Content $configPath) -replace '^default_agent:.*$', "default_agent: $defaultAgent" |
        Set-Content $configPath -Encoding utf8
    Write-Host ''
    Write-Host "default_agent put back to '$defaultAgent'." -ForegroundColor DarkGray
}

Write-Host ''
Write-Host 'Hand these to the Watchdog as <DESK>_RUNTIME_ARN and redeploy it:' -ForegroundColor Yellow
foreach ($d in $arns.Keys) { Write-Host ("  {0}_RUNTIME_ARN={1}" -f $d.ToUpper(), $arns[$d]) }
