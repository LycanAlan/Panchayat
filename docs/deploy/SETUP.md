# Setup: everything that has to exist before Panchayat runs on AWS

Owner: Ali. Companion to `docs/DEPLOY.md`, which covers the deploy command
itself. This file is the **infrastructure** checklist — what has to exist in
the account, in what order, and what each stage buys you.

Written 12 Sep 2026 against a real, half-configured account. Where a step was
executed, it says so. Where it was not, it says that too.

---

## Read this first: four stages, and only the first is blocking

Each stage turns on one execution path. **Stage 1 is the only one standing
between us and "it is deployed."** The rest can follow while the frontend is
being built.

## DEPLOYED — 13 Sep, `ap-south-2` (Hyderabad)

```
arn:aws:bedrock-agentcore:ap-south-2:699073937307:runtime/panchayat-3FFhtr5OfG
```

**Verified live against the real DynamoDB table**: a report routes to BWSSB with
its citation, drafts to the Assistant Engineer at tier 1, sets an SLA deadline,
and writes 5 rows. `list_cases` reads it back, `approve` records a signature,
and a second approval from another member is refused with the original
signatory intact.

**THE QUOTA IS PER-REGION, and that is what unblocked us.** Ali found it by
checking Hyderabad in the console after us-east-1, us-west-2, eu-west-1 and
ap-south-1 all returned `maxAgents limit exceeded`. ap-south-2 sits at full AWS
defaults — Total Agents 1,000, image size 2,048 MB, nothing zeroed. An earlier
note in this file said region switching would not help; that was wrong, and it
was wrong because four regions were tested and treated as "all".

Happy side effect: ap-south-2 is in India, so CLAUDE.md's *"our data stays in
ap-south-1"* claim is now true in spirit — the table and the runtime are both
in-country. The model calls still are not, and never were.

**Observability works** -- AgentCore instruments the runtime itself. See "The
otel trap" below; an earlier note here claiming otherwise was wrong.

| Stage | Turns on | State |
|---|---|---|
| **1. Runtime** | the request path — a household reports, we route and draft | **DONE, live in ap-south-2** |
| **2. Scheduler** | the temporal path — the SLA clock, breach, escalation | **DONE, live in ap-south-2** |
| **3. Streams** | the ambient path — clustering | handler exists; needs a Lambda + event-source mapping |
| **4. Desks** | the institution simulators over A2A | runs locally today, no cloud needed |

---

## Stage 0 — what already exists, verified 12 Sep

Nothing to do here. Recorded so nobody rebuilds it.

- **Account** `699073937307`, IAM user `ali`, local profile `panchayat`
  (`~/.aws/config` → region `us-east-1`).
- **DynamoDB table `panchayat`** in `us-east-1`: `ACTIVE`, keys `PK`/`SK`,
  **`GSI1` present**, **streams enabled** with `NEW_IMAGE`, PAY_PER_REQUEST,
  0 items. The ambient path's data source is already on.
- **The code**: 416 passed, 37 skipped, `ruff` clean.
- **AgentCore control plane reachable** — `ListAgentRuntimes` answers.
- **`agentcore configure` has been run** and wrote `.bedrock_agentcore.yaml`
  (gitignored — it holds absolute paths to this machine).

---

## Stage 1 — the runtime. THIS IS THE BLOCKER

### 1.1 Grant the deployer permissions  ← **needs someone with admin**

This is the only step I cannot do from here, and everything waits on it.

`agentcore deploy` fails with:

```
AccessDeniedException: User: arn:aws:iam::699073937307:user/ali
is not authorized to perform: ecr:CreateRepository
```

Probed every relevant action. `ali` can read and cannot build:

| | |
|---|---|
| **OK** | `dynamodb:*` on the table, `ecr:DescribeRepositories`, `s3:ListBuckets`, `logs:*`, `bedrock-agentcore:ListAgentRuntimes` |
| **DENIED** | `ecr:GetAuthorizationToken`, `ecr:CreateRepository`, `codebuild:*`, all of `iam:*` — it cannot even read its own policies |

Three families missing: **ECR write, CodeBuild, IAM role creation.** The
toolkit auto-creates two roles (runtime execution + CodeBuild service), so
`iam:CreateRole` and `iam:PassRole` are not optional.

**This is the fixable kind.** CLAUDE.md's rule: `AccessDeniedException` is a
missing policy on our user. The Bedrock model block is
`ValidationException: Operation not allowed`, which is account-level and is
not this.

**Do it in the console** (sign in as root or any admin on `699073937307`).

**Mind the size limit — this bites immediately.** An **inline** policy on a
user is capped at **2,048 characters**, and `deployer-policy.json` is 2,377
(IAM excludes whitespace when it counts, so reformatting will not save you).
Two ways through, both fine:

**A. Managed policy — takes the full file, 6,144-character cap:**

    IAM → Policies → Create policy → JSON
      → paste docs/deploy/deployer-policy.json
      → name it `panchayat-deployer` → Create
    IAM → Users → ali → Add permissions → Attach policies directly
      → select `panchayat-deployer` → Add

**B. Inline — paste `docs/deploy/deployer-policy-compact.json` instead** (854
characters):

    IAM → Users → ali → Add permissions → Create inline policy
      → JSON tab → paste docs/deploy/deployer-policy-compact.json
      → name it `panchayat-deployer` → Create

The compact version collapses ECR, CodeBuild, logs and AgentCore to
service-level wildcards. **It deliberately does NOT collapse `iam:`** — those
stay ten named actions scoped to the toolkit's role-name prefixes, because
`iam:*` on a user is a privilege-escalation path and worth 300 characters.

Either policy is scoped on purpose: S3 is limited to the single CodeBuild
source bucket, IAM to the roles the toolkit actually creates.
`AdministratorAccess` also works and is one click — fine for a throwaway
hackathon account, just make it a decision.

**Then confirm it landed** before burning a deploy:

```bash
export AWS_PROFILE=panchayat
aws ecr get-authorization-token --region us-east-1 >/dev/null && echo "ECR OK"
aws codebuild list-projects --region us-east-1 >/dev/null && echo "CodeBuild OK"
```

### 1.2 Deploy

```bash
export AWS_PROFILE=panchayat
export PYTHONIOENCODING=utf-8              # mandatory on Windows, see DEPLOY.md
export AGENTCORE_SUPPRESS_RECOMMENDATION=1

agentcore deploy --agent panchayat
```

Builds ARM64 in CodeBuild. **No Docker needed or wanted.** First run creates
the ECR repo, both roles, the CodeBuild project, and the runtime — several
minutes.

#### Blocked here on 12 Sep — CodeBuild quota is zero

```
AccountLimitExceededException: Cannot have more than 0 builds in queue
for the account
```

Everything up to the build succeeded and **persists**, so a retry resumes from
here: the ECR repo `bedrock-agentcore-panchayat`, the runtime execution role
`AmazonBedrockAgentCoreSDKRuntime-us-east-1-f521b6c81b`, the CodeBuild role
`...SDKCodeBuild-us-east-1-f521b6c81b`, the project
`bedrock-agentcore-panchayat-builder`, and the uploaded source zip.

The project builds on **`ARM_CONTAINER` / `BUILD_GENERAL1_MEDIUM`**
(`aws/codebuild/amazonlinux2-aarch64-standard:3.0`) — that is the quota to
raise. Service Quotas → AWS CodeBuild → the ARM concurrent-builds entry →
Request increase.

**CodeBuild was never the real blocker.** Proven on 12 Sep by going around it:
`direct_code_deploy` needs neither CodeBuild nor ECR, ran the entire pipeline
successfully, and died on the LAST call:

```
ServiceQuotaExceededException: CreateAgentRuntime
maxAgents limit exceeded for account 699073937307
```

**With zero agent runtimes in existence** — `list-agent-runtimes` returns 0 in
us-east-1, us-west-2 and ap-south-1. The account's agent quota is zero, so the
container path would have hit this same wall after a successful build.

**Treat this as one problem, not four.** Four unrelated AWS services are gated
on this account and not one of them is IAM:

| Service | Symptom |
|---|---|
| Bedrock model data plane | `ValidationException: Operation not allowed` (case 178898467100367) |
| AgentCore Memory | `AccessDenied ... contact customer support` |
| CodeBuild | concurrent builds = 0 |
| **AgentCore Runtime** | **`maxAgents` = 0, with 0 agents existing** |

That is an account pending validation, not four coincidences. **No engineering
workaround exists** — the last one is the create call itself, and every deploy
path ends there. This is a support conversation, not a quota form and not a
code change.

**Ask support to validate the account**, naming all four. Raising `maxAgents`
alone is the minimum that unblocks a deploy; the Bedrock data plane is what
unblocks the model calls.

**Nothing above is a defect in the repo**, and the pipeline is proven up to
that wall — see below.

#### `direct_code_deploy` — RUN 12 Sep, and everything worked but the last call

Equally AWS — same Bedrock AgentCore Runtime, same `/invocations` contract.
AWS runs our source on a managed Python runtime instead of building a
container, so it **needs neither CodeBuild nor ECR**.

**The entire pipeline is proven.** Measured, in order:

```
✓ Reusing existing execution role      AmazonBedrockAgentCoreSDKRuntime-...
✓ Dependencies installed with uv       aarch64-manylinux2014 (cross-compiled)
✓ Deployment package ready             88.31 MB
✓ Uploaded to S3                       .../panchayat/deployment.zip
✓ OpenTelemetry instrumentation enabled (aws-opentelemetry-distro detected)
✗ CreateAgentRuntime                   maxAgents limit exceeded
```

So: **uv cross-compiles our dependencies for Linux ARM64 from an amd64 Windows
box**, the package builds and uploads, and the toolkit auto-detects our otel
pin. Only the create call fails, and it fails on account quota.

When the account clears this is one command. Nothing needs rebuilding — the
dependency zip is cached locally and the package is already in S3.

Checked against the installed toolkit rather than assumed:

- **`PYTHON_3_12` is supported.** Our `numpy>=2.5.3` floor is fine.
- **OpenTelemetry survives.** `package.py` scans requirements for
  `aws-opentelemetry-distro` (we pin `0.19.0`) and `build_entrypoint_array()`
  then emits `["opentelemetry-instrument", "app.py"]` — byte for byte the
  Dockerfile's CMD. Observability is not lost.

**What IS lost is the Dockerfile's `ENV` block**, and two of those are
load-bearing enough to fail silently:

**Two prerequisites on Windows, both discovered the hard way:**

```bash
pip install uv        # direct_code_deploy resolves deps with uv, hard requirement
export PATH="$PWD/scripts:$PATH"    # puts our `zip` shim on PATH
```

`uv` is real — the toolkit shells out to it to cross-compile dependencies for
Linux ARM64. `zip` is **not**: `agentcore` refuses to start without a `zip` on
PATH (`shutil.which("zip")`, two places) and then never executes one, because
`utils/runtime/package.py` builds every archive with Python's `zipfile` module.
Stock Windows has no `zip`, so that spurious check makes the toolkit's own
recommended path unreachable. `scripts/zip.cmd` + `scripts/zip_shim.py` satisfy
it with a real working implementation rather than an empty stub — an empty one
would upload nothing the day the toolkit does call it.

**Changing deployment type needs the local config cleared first.** The CLI
refuses (`Cannot change deployment type from 'container' to ...`) based purely
on `deployment_type` in `.bedrock_agentcore.yaml` — it is a client-side guard,
not an AWS constraint; `UpdateAgentRuntime` swaps the artifact on the same
agent id happily. **Do not run `agentcore destroy` to get around it**: that
deletes the ECR repository and IAM roles you want to keep. Delete
`.bedrock_agentcore.yaml` and `.bedrock_agentcore/` instead, which is local
state only.

```bash
agentcore configure --entrypoint app.py --name panchayat \
  --deployment-type direct_code_deploy --runtime PYTHON_3_12 \
  --region us-east-1 --requirements-file requirements.txt \
  --disable-memory --non-interactive

agentcore deploy --agent panchayat \
  --env PANCHAYAT_BACKEND=dynamodb \
  --env DOCKER_CONTAINER=1 \
  --env TIME_SCALE=1
```

#### The otel trap — why `--disable-otel` is on the configure line

The agent runtime CREATED fine and then the endpoint refused to start:

```
Agent endpoint create failed: OpenTelemetry instrumentation executable not
found. The ZIP file requires open-telemetry dependencies, but none are present.
```

Both halves of that are the toolkit arguing with itself. `package.py` scans
`requirements.txt`, finds our `aws-opentelemetry-distro` pin, and sets the
entrypoint to `["opentelemetry-instrument", "app.py"]`. But it installs
dependencies with **uv into a target directory**, and a `--target` install does
not create console-script executables — so `opentelemetry-instrument` is never
in the zip it just built. It requires a binary its own packaging method cannot
produce. Same family as the phantom `zip` check.

`--disable-otel` makes `build_entrypoint_array()` emit `["app.py"]` and the
endpoint comes up.

**AND THE COST TURNED OUT TO BE ZERO — checked, after this was first written
as a loss.** `--disable-otel` removes the wrapper from the entrypoint. It does
not remove instrumentation, because **AgentCore instruments the process
itself**. The runtime's logs carry resource attributes we never configured:

```
telemetry.auto.version : 0.19.0-aws
aws.service.type       : gen_ai_agent
cloud.platform         : aws_bedrock_agentcore
```

and our own `panchayat`-scope lines from `core/tags.py` arrive with
`otelTraceID` populated and `otelTraceSampled: true`. Tracing works.

An earlier version of this section claimed the deployed agent "emits no
traces". That was inferred from the flag name rather than measured, and it was
wrong.

`app.py::_start_observability()` exists as the in-process equivalent of the
wrapper — `opentelemetry-instrument`'s `sitecustomize.py` is two lines, import
`initialize` and call it, so no console script is needed. **Leave it off on
AgentCore**: running it logs *"Attempting to instrument while already
instrumented"*, and a `Failed to export span batch code: 400` appeared in the
same window. It is kept for `handlers/temporal.py` and the ambient handler,
which run on Lambda where nothing instruments them for us — set
`PANCHAYAT_OTEL=1` there.

- **`PANCHAYAT_BACKEND`** defaults to `memory`. Omit it and the deploy looks
  perfectly healthy while every case evaporates between invocations and the
  DynamoDB table stays empty.
- **`DOCKER_CONTAINER=1`** is what makes `app.run()` bind `0.0.0.0`.
  `bedrock_agentcore/runtime/app.py:662` picks the host from `/.dockerenv` or
  that variable and otherwise binds `127.0.0.1` — nothing promises a managed
  runtime provides the first. Wrong bind = liveness fails with no application
  error anywhere to read.

The real cost is not technical, it is repeatability: three settings that the
Dockerfile records in commented detail become flags on a command line, where
they are easy to forget. If we go this way, that command belongs in a script,
not in someone's shell history.

### 1.3 Give the runtime its table

The auto-created execution role gets ECR pull, CloudWatch and the AgentCore
trust relationship. **It does not get DynamoDB.** Until you do this, every
request 500s on the first read.

Find the role (`agentcore status --agent panchayat` prints it, or IAM → Roles →
filter `AmazonBedrockAgentCore`), then:

    IAM → Roles → <that role> → Add permissions → Create inline policy
      → JSON → paste docs/deploy/runtime-table-policy.json
      → name it `panchayat-table` → Create

**That policy now also carries `scheduler:CreateSchedule` and `iam:PassRole`,
and it needs to.** `graph/request_path.py` schedules the case's FIRST wake from
inside the runtime — every later one is created by the Watchdog Lambda, but not
that one. Without these two the report succeeds, the trace says TRACKING, and
the `create_schedule` call fails with AccessDenied: the case gets a deadline
nothing will ever wake it for. `iam:PassRole` is scoped by condition to
`scheduler.amazonaws.com` so the runtime can hand EventBridge the
`panchayat-scheduler` role and nothing else.

**`dynamodb:*Item` is not a substitute.** IAM globs match literally: `*Item`
covers `PutItem`/`GetItem`/`UpdateItem`/`DeleteItem` but **not
`TransactWriteItems`** — different word, plural. `core/store.py` uses
transactions in `add_household_to_case`, `split_case` and `append_consent`.
A role built from a `*Item` glob serves the single-household demo perfectly and
throws AccessDenied on the first *merged* case, which is the demo that matters.
The shipped policy lists it explicitly.

### 1.4 Prove it

```bash
agentcore status --agent panchayat

agentcore invoke --agent panchayat '{"action":"health"}'

agentcore invoke --agent panchayat '{
  "household_id":"hh_001","member_id":"mem_001","language":"en",
  "segment":"ward12-4thcross",
  "text":"No water in the tank for three days"}'
```

**Expect** `case_status: "drafted"`, `authority: "BWSSB"`, a `citation`,
`filed_to` naming the Assistant Engineer, `filed_tier: 1`, and an
`sla_deadline`. Anything with `unrouted_reason` set means routing failed —
`"no_segment"` means you left `segment` out, and it is required.

**After this stage the endpoint is live and the frontend has something real to
call.** Stages 2–4 are not blocking that.

---

## Stage 2 — the scheduler. DONE 13 Sep, verified end to end

```
Lambda    panchayat-watchdog          arm64, python3.12, handlers.temporal.handler
Roles     panchayat-watchdog-exec     table + logs + books the next wake
          panchayat-scheduler         EventBridge assumes this to invoke the Lambda
```

**Proven by filing a real report at the live endpoint**, not from a test:

```
report          -> case_ea0c49e96c9e, drafted, SLA 2026-09-19
EventBridge     -> pnc-case_ea0c49e96c9e-expire_draft
                   at(2026-09-19T20:37:48) -> panchayat-watchdog
                   ActionAfterCompletion: DELETE
fire the wake   -> {"woken": 1, "failed": 0}
DynamoDB        -> status drafted -> dormant
```

An unsigned draft that expired becomes DORMANT, which is the correct
transition. **The chain Runtime → EventBridge → Lambda → Watchdog → DynamoDB
works.**

### Two things that would have broken it quietly

**The package is 15.9 MB, not 88 MB.** `handlers/temporal.py` needs far less
than `app.py`: measured by importing it and diffing `sys.modules`, it wants
our code, numpy, and boto3 — which the Lambda runtime provides. **No strands,
no bedrock_agentcore, no opentelemetry.** Those are most of the AgentCore
package and none is on this path. arm64 because numpy 2.5.3 publishes no
manylinux_2_17 x86_64 wheel.

**The Lambda's own role needs `scheduler:CreateSchedule` and `PassRole`, and
that is not a copy-paste of the Runtime's.** `climb()` books the NEXT wake and
`climb()` runs INSIDE this Lambda. A role with only DynamoDB and logs would
chase a case exactly once and then go silent — which reads as success.
`WATCHDOG_LAMBDA_ARN` and `SCHEDULER_ROLE_ARN` are set on the Lambda too, for
the same reason; without them `RealClock.schedule()` raises
`SchedulerNotConfigured` on the second hop.

### Rebuilding the package

```bash
uv pip install --target build --python-platform aarch64-manylinux_2_28   --python-version 3.12 --only-binary=:all: numpy pyyaml python-dotenv
cp -r agents core graph handlers institutions data build/
# zip build/ and: aws lambda update-function-code --function-name panchayat-watchdog
```

### Historical — what this said before it was done

### 2.1 Package and create the Watchdog Lambda

Entry point already exists: **`handlers/temporal.py`**, handler
`handlers.temporal.handler`. It understands both a direct EventBridge payload
and an SQS-wrapped `Records[].body`, and raises `TransientWakeFailure` for
retryable problems.

- Function name **`panchayat-watchdog`** (the shipped policies assume it; if
  you rename it, edit `docs/deploy/scheduler-role-policy.json` to match)
- Runtime Python 3.12, timeout ~60s
- Package the repo plus `requirements.txt` deps as a zip or container image
- Environment: `PANCHAYAT_BACKEND=dynamodb`, `PANCHAYAT_TABLE=panchayat`,
  `TIME_SCALE=1`
- Execution role: `AWSLambdaBasicExecutionRole` **plus
  `docs/deploy/runtime-table-policy.json`** — it reads and writes the same
  cases

### 2.2 Create the role EventBridge Scheduler assumes

Scheduler needs its own role to invoke that Lambda.

```bash
aws iam create-role --role-name panchayat-scheduler \
  --assume-role-policy-document file://docs/deploy/scheduler-role-trust.json

aws iam put-role-policy --role-name panchayat-scheduler \
  --policy-name invoke-watchdog \
  --policy-document file://docs/deploy/scheduler-role-policy.json
```

The trust policy is conditioned on `aws:SourceAccount` so nothing outside this
account can assume it.

### 2.3 Hand both ARNs back to the runtime

`core/clock.py` reads exactly two variables and refuses to call EventBridge
with an empty ARN — deliberately, so a misconfiguration is loud:

```bash
agentcore deploy --agent panchayat \
  --env WATCHDOG_LAMBDA_ARN=arn:aws:lambda:us-east-1:699073937307:function:panchayat-watchdog \
  --env SCHEDULER_ROLE_ARN=arn:aws:iam::699073937307:role/panchayat-scheduler
```

Catch `SchedulerNotConfigured` specifically if you handle it anywhere —
catching broadly hides a real EventBridge outage.

### 2.4 Two things this stage used to leave broken — both now closed

**`check_closure` is scheduled.** `climb()` books it at the statutory
deadline, alongside `check_sla`. This section used to say nothing scheduled
it and the disputed-closure moment could only fire from tests.

**And it now asks the desk before deciding.** `reconcile_closure` is
documented as "the institution says resolved; live claims from other
households say otherwise" — but nothing polled a desk, so only the second
half was measured, and on a one-household street that half is always "nobody
contradicts it". Every case was therefore written `RESOLVED`, which is
terminal, by an office that had answered nothing. The Watchdog now takes a
`closed(authority, external_ref)` seam, wired in `handlers/temporal.py` from
`institutions.client.build_closure_probe()`, exactly as `submit` is. **With
the desks in Stage 4 not running, that probe reports UNREACHABLE and no case
self-resolves** — which is the correct behaviour, not a regression.

### 2.5 If you are reusing a table that has claims in it from before 13 Sep

`GSI1PK` on a claim used to be built from the raw segment and is now folded
to lower case (issue #17), so rows written before that land in a partition
`claims_in_window` no longer queries. **They are invisible to clustering, in
silence.** For a table with a handful of demo rows the fix is to re-`put_claim`
them; for a fresh table there is nothing to do. Deleting and recreating the
table (`scripts/create_table.py`) is the fastest path and the one we took.

---

## Stage 3 — streams, for clustering

**`handlers/ambient.py` now exists** (`handler`, same shape as the temporal
one). The table's streams were already on; this is what finally reads them.
Without this stage the request path still works and **clustering never runs** —
measured before the handler landed: three households reporting one fault on one
street opened three cases, corroboration 1, 1, 1.

### 3.1 Package and create the Lambda

Same zip as Stage 2, different entry point: `handlers.ambient.handler`.

- Name: `panchayat-ambient`
- Runtime: Python 3.12, **arm64**
- Timeout: 60s is ample — the common case does arithmetic and returns
- Execution role: `AWSLambdaBasicExecutionRole` **plus** the same
  `runtime-table-policy.json` (it reads claims and writes cases), **plus**
  `dynamodb:GetRecords`, `dynamodb:GetShardIterator`,
  `dynamodb:DescribeStream` and `dynamodb:ListStreams` on the table's
  **stream** ARN — that is a different ARN from the table's.

### 3.2 The event-source mapping, and the one flag that matters

```bash
STREAM_ARN=$(aws dynamodb describe-table --table-name panchayat \
  --query 'Table.LatestStreamArn' --output text)

aws lambda create-event-source-mapping \
  --function-name panchayat-ambient \
  --event-source-arn "$STREAM_ARN" \
  --starting-position LATEST \
  --batch-size 10 \
  --maximum-retry-attempts 3 \
  --function-response-types ReportBatchItemFailures \
  --filter-criteria '{"Filters":[{"Pattern":"{\"eventName\":[\"INSERT\"]}"}]}'
```

**`--function-response-types ReportBatchItemFailures` is not optional.** The
handler returns `{"batchItemFailures": [...]}` naming only the records worth
redelivering. Without this flag AWS ignores that return value entirely and
treats every invocation as a success — so a claim that failed on a throttle is
dropped silently instead of retried, and clustering quietly misses households.

Why the handler reports failures rather than raising, unlike the temporal one:
a DynamoDB stream retries the **whole batch from the same position**, so one
poison record would block every later claim on that shard until it ages out
(24h). Clustering would stop for a day — the exact failure the handler exists
to prevent, recreated by its own error handling.

The `INSERT` filter is belt-and-braces: the handler filters again on
`eventName` and on a `CLAIM#` partition key, so widening the console filter to
debug something cannot make it act on case or filing rows.

### 3.3 Check it

Report a fault twice on one curated street, then:

```bash
aws logs tail /aws/lambda/panchayat-ambient --follow
```

A merge prints `MERGING     ambient     -> 1 case(s) upgraded from 1 stream
record(s)`. Nothing at all means the claims did not correlate — check that both
claims carry a `feeder_id` (the request path fills it from `remedy.lookup`;
an uncurated segment leaves it empty and those claims cannot corroborate).

---

## Stage 4 — the institution desks

`institutions/server.py` runs the simulated desks as **separate processes with
their own state** — that separation is the trust boundary, not decoration
(CLAUDE.md: they must never touch our table).

**`bwssb` is deployed, 13 Sep.** It runs as an AgentCore A2A server,
`panchayat_desk_bwssb`, and a filing signed on the live site came back with
ticket `BWSSB-100002`. The other four still run locally.

```bash
# one desk, one runtime. PANCHAYAT_DESK picks which.
agentcore configure -n panchayat_desk_bwssb -e desk_app.py -p A2A -r ap-south-2 \
  -dt direct_code_deploy -rt PYTHON_3_12 -rf requirements-prod.txt -ni -do -dm \
  -er arn:aws:iam::699073937307:role/panchayat-desk-exec \
  -s3 bedrock-agentcore-codebuild-sources-699073937307-ap-south-2
agentcore launch --agent panchayat_desk_bwssb \
  -env PANCHAYAT_DESK=bwssb -env PANCHAYAT_MODEL=gemini -env GEMINI_API_KEY=... \
  -env PANCHAYAT_DESK_TABLE=panchayat-desks -env PANCHAYAT_TABLE=panchayat
# then hand the ARN to the Watchdog as <DESK>_RUNTIME_ARN and redeploy it.
```

**Four things that will bite whoever deploys the other four.** The entrypoint
must sit at the repo root (`desk_app.py`): configured as
`institutions/a2a_runtime.py`, the toolkit records a Windows backslash and the
endpoint fails with "entrypoint could not be found in your artifact" **after**
creating the runtime. The agent name takes no hyphens. A desk needs its own
execution role, because the main runtime's role can read our case table. And
the Watchdog package must bundle `boto3` and allow 180s, since an AgentCore
cold start plus a model call does not fit in 60.

**Locally, they are still five processes.** `institutions/client.py` uses
`<DESK>_RUNTIME_ARN` when set and otherwise resolves each desk by endpoint
variable, falling back to the port its profile declares:

    WARD_ENDPOINT=http://localhost:9001
    WATER_ENDPOINT=http://localhost:9002     # the desk is "bwssb", the profile is water
    SCHOOL_ENDPOINT=http://localhost:9003
    VENDOR_ENDPOINT=http://localhost:9004
    PAYMENTS_ENDPOINT=http://localhost:9005

A **cloud-deployed** runtime cannot reach `localhost` desks. So either run the
end-to-end filing demo locally, or give the desks public endpoints and set
these variables at deploy time. Decide before recording the video.

---

## Environment variable reference

Every variable the code actually reads, verified by grep — not from
`.env.example`, which lists several nothing consumes (`MODEL_SMALL`,
`MODEL_MID`, `MODEL_LARGE`, `TAU`) and is stale.

| Variable | Default | What it does |
|---|---|---|
| `PANCHAYAT_BACKEND` | `memory` | `dynamodb` in the image. The whole suite runs on `memory` with no AWS. |
| `PANCHAYAT_TABLE` | `panchayat` | table name |
| `PANCHAYAT_DDB_ENDPOINT` | unset | point at DynamoDB Local; unset in production |
| `TIME_SCALE` | `1` | `1` is production. `86400` = one statutory day per real second, the demo setting. |
| `WATCHDOG_LAMBDA_ARN` | empty | Stage 2. Empty ⇒ `SchedulerNotConfigured`. |
| `SCHEDULER_ROLE_ARN` | empty | Stage 2. Same. |
| `PANCHAYAT_MODEL` | `bedrock` | `anthropic` swaps provider in one variable |
| `ANTHROPIC_API_KEY` | — | only with `PANCHAYAT_MODEL=anthropic` |
| `PANCHAYAT_BEDROCK_REGION` | `us-east-1` | `ap-south-1` has no Anthropic inference profiles |
| `AWS_REGION` | — | `us-east-1` |
| `MODEL_EMBED` | — | embeddings; unused while Bedrock is blocked |
| `PANCHAYAT_BIND_HOST` / `PANCHAYAT_PUBLIC_HOST` | — | A2A servers |
| `PANCHAYAT_ALLOW_DESTRUCTIVE_RESET` | unset | guards `store.reset()`. **Never set in production.** |

**Secrets never go in any of these files.** `.env` is gitignored and the
pre-commit hook refuses AWS keys. If a key has to move between people, it goes
privately — not the group chat, not the repo, not a Devpost screenshot.

---

## Two decisions to make, neither blocking

**The table is in `us-east-1`; CLAUDE.md says data stays in `ap-south-1`.**
It has **0 items**, so moving is free today and will not be later. Either move
it or update the claim — but shipping the contradiction is a data-residency
claim in a civic-tech pitch, which is exactly what a judge probes.

**The deployed API is write-only.** The entrypoint understands `health` and
"a household is reporting". There is no `get_case`, no `list_cases`, no
`approve`. A frontend can render the one response it gets and nothing after.
Adding those three actions to `app.py` is ~an hour, and `approve` also closes
the signature-capture gap that hard rule 4 requires and nothing currently calls.
Do it **after** Stage 1 — never bundle new code into a first-ever deploy, or a
failure tells you nothing about which half broke.
