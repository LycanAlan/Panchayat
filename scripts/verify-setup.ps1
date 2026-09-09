# Panchayat -- verify your machine is actually ready.
#
#   powershell -ExecutionPolicy Bypass -File scripts\verify-setup.ps1
#
# Run this before you write any code. Every teammate runs it. If a check fails,
# say so in the group rather than working around it -- a half-configured machine
# on Day 1 becomes a mystery bug on Day 3.

$ErrorActionPreference = "Continue"
$repo = git rev-parse --show-toplevel 2>$null
if ($repo) { Set-Location $repo }

$region = "us-east-1"
$table = "panchayat"
$profile = "panchayat"
$pass = 0
$fail = 0

function Check($name, $ok, $detail, $fixHint) {
    if ($ok) {
        Write-Host "  PASS  " -ForegroundColor Green -NoNewline
        Write-Host "$name" -NoNewline
        if ($detail) { Write-Host "  $detail" -ForegroundColor DarkGray } else { Write-Host "" }
        $script:pass++
    } else {
        Write-Host "  FAIL  " -ForegroundColor Red -NoNewline
        Write-Host "$name"
        if ($detail) { Write-Host "        $detail" -ForegroundColor DarkGray }
        if ($fixHint) { Write-Host "        fix: $fixHint" -ForegroundColor Yellow }
        $script:fail++
    }
}

Write-Host ""
Write-Host "  Panchayat setup check" -ForegroundColor Cyan
Write-Host "  ---------------------"
Write-Host ""

# --- toolchain ---
$py = (& python --version 2>&1) -join ""
Check "python 3.10+" ($py -match "3\.(1[0-9]|[2-9][0-9])") $py "install Python 3.12"

$awsv = (& aws --version 2>&1) -join ""
Check "aws cli v2" ($awsv -match "aws-cli/2") $awsv "winget install -e --id Amazon.AWSCLI, then reopen the terminal"

# --- venv + deps ---
$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $deps = & $venvPy -c "import strands, bedrock_agentcore, boto3, numpy, yaml; print('ok')" 2>&1
    Check "dependencies" ($deps -match "ok") "strands, bedrock_agentcore, boto3, numpy, yaml" "pip install -r requirements.txt"
} else {
    Check "virtualenv" $false ".venv not found" "python -m venv .venv"
}

# --- contracts ---
$contracts = & python -c "from core.types import Claim, Service; from core.clock import get_clock; c=Claim(segment='ward12-4thcross', service=Service.WATER); print(c.gsi1pk())" 2>&1
Check "contracts import" ($contracts -match "SEG#ward12") "$contracts" "run from the repo root"

# --- git hooks ---
$hooks = git config core.hooksPath 2>$null
Check "git hooks enabled" ($hooks -eq ".githooks") "core.hooksPath=$hooks" "powershell -ExecutionPolicy Bypass -File scripts\setup-hooks.ps1"

# --- aws identity ---
$ident = & aws sts get-caller-identity --profile $profile --output text 2>&1
$identOk = $LASTEXITCODE -eq 0
Check "aws credentials" $identOk $(if ($identOk) { ($ident -split "\s+")[-1] } else { "profile '$profile' not usable" }) "aws configure --profile $profile"

# --- dynamodb ---
if ($identOk) {
    $status = & aws dynamodb describe-table --table-name $table --region $region --profile $profile --query "Table.TableStatus" --output text 2>&1
    Check "dynamodb table" ($status -eq "ACTIVE") "$table = $status" "Ali: run the create-table command in docs/SETUP.md 1.4"

    if ($status -eq "ACTIVE") {
        $gsi = & aws dynamodb describe-table --table-name $table --region $region --profile $profile --query "Table.GlobalSecondaryIndexes[0].IndexName" --output text 2>&1
        Check "GSI1 present" ($gsi -eq "GSI1") "index=$gsi" "Pattern Watch queries this. Recreate the table with the GSI."

        $stream = & aws dynamodb describe-table --table-name $table --region $region --profile $profile --query "Table.StreamSpecification.StreamEnabled" --output text 2>&1
        Check "stream enabled" ($stream -eq "True") "stream=$stream" "Pattern Watch triggers off this. Enable it now, not on Day 3."
    }

    # --- bedrock ---
    $models = & aws bedrock list-foundation-models --region $region --profile $profile --query "length(modelSummaries)" --output text 2>&1
    Check "bedrock reachable" ($models -match "^\d+$") "$models models visible" "check AmazonBedrockFullAccess on your IAM user"

    $titan = & aws bedrock list-foundation-models --region $region --profile $profile --query "modelSummaries[?contains(modelId,'titan-embed-text-v2')].modelId" --output text 2>&1
    Check "titan listed" ($titan -match "titan-embed") "$titan" "Bedrock > Model access > enable Titan Text Embeddings V2 (Kartik is blocked without it)"

    # Listing a model does NOT mean you can call it. A fresh account can list
    # 123 models and invoke none of them. Only an actual invoke proves access.
    $venvPy = Join-Path $repo ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        $probe = & $venvPy -c @"
import boto3
try:
    boto3.Session(profile_name='panchayat', region_name='us-east-1').client('bedrock-runtime').converse(
        modelId='us.amazon.nova-lite-v1:0',
        messages=[{'role':'user','content':[{'text':'ok'}]}],
        inferenceConfig={'maxTokens':5})
    print('INVOKE_OK')
except Exception as e:
    print(type(e).__name__ + ': ' + str(e)[:120])
"@ 2>&1
        Check "model invocable" ($probe -match "INVOKE_OK") "$probe" "Bedrock > Model access > Modify. On a new account this can also be a verification hold -- wait and retry."
    }
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host "  All $pass checks passed. You are ready to build." -ForegroundColor Green
} else {
    Write-Host "  $pass passed, $fail failed." -ForegroundColor Yellow
    Write-Host "  Post the failures in the group. Do not work around them." -ForegroundColor DarkGray
}
Write-Host ""
