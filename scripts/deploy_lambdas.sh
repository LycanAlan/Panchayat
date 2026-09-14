#!/usr/bin/env bash
# Package and redeploy the two Lambdas that run our code from one zip:
#
#   panchayat-watchdog   handlers.temporal.handler   (the temporal path)
#   panchayat-ambient    handlers.ambient.handler    (clustering, on the stream)
#
#   AWS_PROFILE=panchayat bash scripts/deploy_lambdas.sh
#
# WHY A SCRIPT. Both fixes in PR #43 were merged and running nowhere: the
# author's machine had no AWS credentials, and there was no written path from
# "merged" to "deployed" for these two functions. Now there is.
#
# Three things that are not obvious and each cost time once:
#
#   1. boto3 MUST be bundled. The Lambda runtime's copy predates
#      bedrock-agentcore's InvokeAgentRuntime, so a package that trusts the
#      runtime's boto3 files nothing and reports every desk unreachable.
#   2. Zip with Python, not Compress-Archive. PowerShell writes backslash entry
#      names, and Linux cannot open "handlers\temporal.py".
#   3. arm64 wheels, because numpy 2.5.3 ships no manylinux_2_17 x86_64 wheel,
#      and the functions are arm64 for that reason.
#
# No strands, no bedrock_agentcore, no opentelemetry: measured by importing
# handlers/temporal.py and diffing sys.modules, none of them is on this path,
# and they are most of the 88 MB. This package is ~16 MB.
#
# Owner: Ali (platform).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
: "${AWS_PROFILE:=panchayat}"; export AWS_PROFILE
REGION="${REGION:-ap-south-2}"

# A fresh, uniquely named directory every run: never reuse and never delete
# a previous one from inside a deploy script.
BUILD="${TMPDIR:-/tmp}/panchayat-lambda-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BUILD"

UV="$ROOT/.venv/Scripts/uv.exe"; [ -x "$UV" ] || UV="$ROOT/.venv/bin/uv"; [ -x "$UV" ] || UV="uv"
"$UV" pip install --quiet --target "$BUILD" \
  --python-platform aarch64-manylinux_2_28 --python-version 3.12 \
  --only-binary=:all: numpy pyyaml python-dotenv boto3

for d in agents core graph handlers institutions data; do cp -r "$ROOT/$d" "$BUILD/"; done

ZIP="$BUILD.zip"
python - "$BUILD" "$ZIP" <<'PY'
import shutil, sys
build, zip_path = sys.argv[1], sys.argv[2]
shutil.make_archive(zip_path[:-4], "zip", build)
PY
echo "package: $(du -h "$ZIP" | cut -f1)  $ZIP"

# The AWS CLI on Windows wants a Windows path even from Git Bash.
ZIPARG="$ZIP"; command -v cygpath >/dev/null && ZIPARG="$(cygpath -w "$ZIP")"

for fn in panchayat-watchdog panchayat-ambient; do
  aws lambda update-function-code --function-name "$fn" --region "$REGION" \
    --zip-file "fileb://$ZIPARG" \
    --query '{fn:FunctionName,mb:CodeSize,status:LastUpdateStatus}' --output json
  aws lambda wait function-updated --function-name "$fn" --region "$REGION"
  echo "$fn: $(aws lambda get-function-configuration --function-name "$fn" --region "$REGION" --query 'LastModified' --output text)"
done
