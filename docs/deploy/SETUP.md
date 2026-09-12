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

| Stage | Turns on | State |
|---|---|---|
| **1. Runtime** | the request path — a household reports, we route and draft | **blocked on one IAM policy** |
| **2. Scheduler** | the temporal path — the SLA clock, breach, escalation | needs a Lambda that is not packaged yet |
| **3. Streams** | the ambient path — clustering | **`handlers/ambient.py` does not exist** |
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

**Do it in the console** (sign in as root or any admin on `699073937307`):

    IAM → Users → ali → Add permissions → Create inline policy
      → JSON tab → paste docs/deploy/deployer-policy.json
      → name it `panchayat-deployer` → Create

That policy is scoped on purpose: ECR and CodeBuild broadly, **IAM narrowed to
the four role-name prefixes the toolkit actually creates**, S3 to the single
CodeBuild source bucket. `AdministratorAccess` also works and is one click —
fine for a throwaway hackathon account, just make it a decision.

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

### 1.3 Give the runtime its table

The auto-created execution role gets ECR pull, CloudWatch and the AgentCore
trust relationship. **It does not get DynamoDB.** Until you do this, every
request 500s on the first read.

Find the role (`agentcore status --agent panchayat` prints it, or IAM → Roles →
filter `AmazonBedrockAgentCore`), then:

    IAM → Roles → <that role> → Add permissions → Create inline policy
      → JSON → paste docs/deploy/runtime-table-policy.json
      → name it `panchayat-table` → Create

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

## Stage 2 — the scheduler, so cases escalate

Without this, `RealClock.schedule()` raises `SchedulerNotConfigured`, no wake
is ever booked, and **a filed case is never chased.** The SLA clock is the
product; this is the stage that makes it true in production.

**Not yet attempted.** Written from what `core/clock.py` and
`handlers/temporal.py` require. Budget real time.

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

### 2.4 Known gap this stage does NOT close

**Nothing schedules `check_closure`.** Verified by grepping every
`clock.schedule()` call. A desk returning `CLOSED` triggers nothing, so the
disputed-closure moment — the peak of the demo video — can still only fire from
tests. Raghav proposes the cadence, the group ratifies. Infrastructure cannot
fix a trigger that was never written.

---

## Stage 3 — streams, for clustering

**Cannot be set up yet: `handlers/ambient.py` does not exist.** The table's
streams are already on and nothing consumes them. `handlers/temporal.py` is the
shape to copy. Kartik + Ali.

Once it exists: a second Lambda plus an event-source mapping from the table's
stream ARN. No new IAM beyond the table policy and
`dynamodb:GetRecords`/`GetShardIterator`/`DescribeStream` on the stream.

---

## Stage 4 — the institution desks

`institutions/server.py` runs the simulated desks as **separate processes with
their own state** — that separation is the trust boundary, not decoration
(CLAUDE.md: they must never touch our table).

**For the demo, run them locally.** No cloud hosting required, and hosting them
would not make the demo more convincing. `institutions/client.py` resolves each
desk by environment variable, falling back to the port its profile declares:

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
