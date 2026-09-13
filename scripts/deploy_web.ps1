<#
.SYNOPSIS
  Build the site, package the web Lambda, create or update it, print its URL.

.DESCRIPTION
  One Lambda (panchayat-web) serves web/dist and forwards POST /api to the
  AgentCore runtime. handlers/web_api.py says why it is one Lambda rather
  than CloudFront + API Gateway.

  NEEDS docs/deploy/web-deployer-policy.json attached to the deploying IAM
  user by an account admin. On 13 Sep `ali` could not read or create Lambda
  function URLs at all. The script stops at the first AccessDenied and names
  that file, rather than leaving a half-built stack.

  Idempotent. Run it again after any change to the site or the handler.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\deploy_web.ps1
#>
param(
  [string]$AwsProfile = 'panchayat',
  [string]$Region = 'ap-south-2',
  [string]$FunctionName = 'panchayat-web',
  [string]$RoleName = 'panchayat-web-exec'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
$uv = Join-Path $root '.venv\Scripts\uv.exe'
$work = Join-Path $env:TEMP 'panchayat-web'
$hint = 'Attach docs/deploy/web-deployer-policy.json to the deploying IAM user, then run this again.'

function Invoke-Aws {
  # A native exe does not throw on a non-zero exit, and in Windows PowerShell
  # 5.1 redirecting its stderr under 'Stop' throws on the first warning line
  # instead. So: Continue here, and check the exit code once, here.
  $ErrorActionPreference = 'Continue'
  $out = & aws @args --profile $AwsProfile --region $Region --output json 2>&1
  if ($LASTEXITCODE -ne 0) {
    $text = ($out | Out-String).Trim()
    if ($text -match 'AccessDenied') { throw "$text`n`n$hint" }
    throw $text
  }
  $json = ($out | Out-String).Trim()
  if ($json) { return $json | ConvertFrom-Json }
}

function Test-Aws {
  # For lookups where "does not exist" is an answer. Any other failure,
  # AccessDenied included, surfaces on the create that follows.
  $ErrorActionPreference = 'Continue'
  & aws @args --profile $AwsProfile --region $Region --output json 2>&1 | Out-Null
  return ($LASTEXITCODE -eq 0)
}

function Write-Ascii([string]$Path, [string]$Text) {
  # No BOM. Windows PowerShell's UTF-8 writes one, and a policy document
  # that starts with one is refused as malformed.
  [IO.File]::WriteAllText($Path, $Text, [Text.Encoding]::ASCII)
}

if (-not (Test-Path $py)) { throw "No .venv under $root. See docs/SETUP.md." }

$runtimeArn = (& $py -c "import sys, yaml; d = yaml.safe_load(open(sys.argv[1], encoding='utf-8')); print(d['agents'][d['default_agent']]['bedrock_agentcore']['agent_arn'])" (Join-Path $root '.bedrock_agentcore.yaml') | Out-String).Trim()
if ($runtimeArn -notmatch '^arn:aws:bedrock-agentcore:') {
  throw 'Could not read the runtime ARN from .bedrock_agentcore.yaml. Has agentcore launch run on this machine?'
}
Write-Host "runtime  $runtimeArn"

Write-Host '1/5  building the site'
Push-Location (Join-Path $root 'web')
try {
  npm ci --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw 'vite build failed' }
} finally {
  Pop-Location
}

Write-Host '2/5  packaging'
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
$build = Join-Path $work 'build'
New-Item -ItemType Directory -Force $build | Out-Null
# boto3 is bundled, not borrowed from the Lambda runtime. The runtime's copy
# lags releases, and one without the bedrock-agentcore data plane fails on the
# first click with UnknownServiceError instead of here.
& $uv pip install --quiet --target $build --python-platform aarch64-manylinux_2_28 --python-version 3.12 --only-binary=:all: boto3
if ($LASTEXITCODE -ne 0) { throw 'bundling boto3 failed' }
Copy-Item (Join-Path $root 'handlers\web_api.py') (Join-Path $build 'web_api.py')
Copy-Item -Recurse (Join-Path $root 'web\dist') (Join-Path $build 'site')
# Python's zipfile, not Compress-Archive: Windows PowerShell 5.1 writes
# backslashes into entry names, and Lambda on Linux cannot find web_api.py.
$zipBase = Join-Path $work 'web'
& $py -c "import shutil, sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2])" $zipBase $build
if ($LASTEXITCODE -ne 0) { throw 'zip failed' }
$zip = "$zipBase.zip"
Write-Host ('     {0:N1} MB' -f ((Get-Item $zip).Length / 1MB))

Write-Host '3/5  execution role'
$trust = Join-Path $root 'docs\deploy\web-lambda-trust.json'
$rolePolicy = Join-Path $work 'role-policy.json'
$template = Get-Content (Join-Path $root 'docs\deploy\web-lambda-role-policy.json') -Raw
Write-Ascii $rolePolicy $template.Replace('RUNTIME_ARN', $runtimeArn)
$newRole = -not (Test-Aws iam get-role --role-name $RoleName)
if ($newRole) {
  Invoke-Aws iam create-role --role-name $RoleName --assume-role-policy-document "file://$trust" | Out-Null
}
Invoke-Aws iam put-role-policy --role-name $RoleName --policy-name invoke-runtime --policy-document "file://$rolePolicy" | Out-Null
$roleArn = (Invoke-Aws iam get-role --role-name $RoleName).Role.Arn

Write-Host '4/5  function'
$envFile = Join-Path $work 'env.json'
Write-Ascii $envFile ('{"Variables":{"PANCHAYAT_RUNTIME_ARN":"' + $runtimeArn + '"}}')
if (Test-Aws lambda get-function --function-name $FunctionName) {
  Invoke-Aws lambda update-function-code --function-name $FunctionName --zip-file "fileb://$zip" | Out-Null
  Invoke-Aws lambda wait function-updated-v2 --function-name $FunctionName
  Invoke-Aws lambda update-function-configuration --function-name $FunctionName --role $roleArn --environment "file://$envFile" --timeout 120 --memory-size 512 | Out-Null
  Invoke-Aws lambda wait function-updated-v2 --function-name $FunctionName
} else {
  # A role minutes old is often not yet assumable by Lambda. That failure
  # names itself, so retry exactly it and nothing else.
  for ($attempt = 1; ; $attempt++) {
    try {
      Invoke-Aws lambda create-function --function-name $FunctionName --runtime python3.12 --architectures arm64 --handler web_api.handler --role $roleArn --timeout 120 --memory-size 512 --environment "file://$envFile" --zip-file "fileb://$zip" | Out-Null
      break
    } catch {
      if ($attempt -ge 5 -or $_.Exception.Message -notmatch 'cannot be assumed') { throw }
      Write-Host '     role not assumable yet, retrying'
      Start-Sleep -Seconds 8
    }
  }
  Invoke-Aws lambda wait function-active-v2 --function-name $FunctionName
}

Write-Host '5/5  public URL'
if (-not (Test-Aws lambda get-function-url-config --function-name $FunctionName)) {
  Invoke-Aws lambda create-function-url-config --function-name $FunctionName --auth-type NONE | Out-Null
}
# Both grants. Lambda authorizes a public URL request against
# lambda:InvokeFunctionUrl AND lambda:InvokeFunction (the second scoped to
# URL calls by --invoked-via-function-url); with only the first, the URL
# answers 403. A rerun finds them already there, which is fine.
$grants = @(
  @('--statement-id', 'public-url', '--action', 'lambda:InvokeFunctionUrl', '--function-url-auth-type', 'NONE'),
  @('--statement-id', 'public-url-invoke', '--action', 'lambda:InvokeFunction', '--invoked-via-function-url')
)
foreach ($grant in $grants) {
  try {
    Invoke-Aws lambda add-permission --function-name $FunctionName --principal '*' @grant | Out-Null
  } catch {
    if ($_.Exception.Message -notmatch 'ResourceConflictException') { throw }
  }
}
$url = (Invoke-Aws lambda get-function-url-config --function-name $FunctionName).FunctionUrl

$api = $url.TrimEnd('/') + '/api'
try {
  $health = Invoke-RestMethod -Method Post -Uri $api -ContentType 'application/json' -Body '{"action":"health"}' -TimeoutSec 120
  Write-Host ('health   ' + ($health | ConvertTo-Json -Compress))
} catch {
  Write-Warning "The URL exists but /api did not answer yet: $($_.Exception.Message)"
}
Write-Host ''
Write-Host "Site: $url"
