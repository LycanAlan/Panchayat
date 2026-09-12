# Deploying to Bedrock AgentCore Runtime

Owner: Ali (platform). Read `CLAUDE.md` first.

## What is verified, and what is not

Honesty first, because a runbook that overstates itself is worse than none.

| Step | State |
|---|---|
| `app.py` serves the AgentCore contract | **tested** — `tests/test_app.py`, real ASGI |
| `GET /ping` | **tested** — through Starlette routing |
| `POST /invocations`, health action | **tested** |
| `POST /invocations`, full spine | **tested** — routes, drafts, tracks, over HTTP |
| Response survives JSON encoding | **tested** — `sla_deadline`, `trace`, `usage` |
| A report with no `segment` degrades, not 500s | **tested** |
| Two concurrent reports | **tested** — full path, no shared `Graph` state |
| Spans carry `case_id` | **tested** — real in-memory exporter |
| One trace per request | **tested** — Strands' own spans included |
| Request path runs with **live creds + blocked Bedrock** | **verified 12 Sep** — completes, 0 tokens |
| `panchayat` table reachable, `GSI1` + streams on | **verified 12 Sep** — ACTIVE, `NEW_IMAGE` |
| `agentcore configure` | **verified 12 Sep** — succeeded, kept our Dockerfile |
| `agentcore deploy` (CodeBuild, arm64) | **BLOCKED 12 Sep** — deployer IAM, see below |
| Image in ECR, runtime live, end-to-end invoke | **NOT verified** — never got past IAM |

So: the application contract is tested and the toolchain is proven up to the
IAM wall. **Nothing has been deployed yet.**

## THE BLOCKER, and it is not code

`agentcore deploy` fails here:

```
AccessDeniedException: User: arn:aws:iam::699073937307:user/ali is not
authorized to perform: ecr:CreateRepository
```

Probed every relevant action on 12 Sep. The `ali` IAM user can read but not
build:

| Action | `ali` |
|---|---|
| `dynamodb:DescribeTable` (and the table's data ops) | **OK** |
| `bedrock-agentcore:ListAgentRuntimes` | **OK** |
| `ecr:DescribeRepositories`, `s3:ListBuckets`, `logs:DescribeLogGroups` | **OK** |
| `ecr:GetAuthorizationToken`, `ecr:CreateRepository` | **DENIED** |
| `codebuild:*` | **DENIED** |
| `iam:*` — cannot even read its own policies | **DENIED** |

Three families are missing: **ECR write, CodeBuild, and IAM role creation.**
The toolkit auto-creates two roles (the runtime execution role and a CodeBuild
service role), so `iam:CreateRole` + `iam:PassRole` are not optional.

**This is CLAUDE.md's fixable kind.** `AccessDeniedException` = a missing
policy on our user. Contrast the Bedrock model block, which is
`ValidationException: Operation not allowed` and is account-level.

### Fixing it

Someone with admin on account `699073937307` attaches
`docs/deploy/deployer-policy.json` to the `ali` user — IAM → Users → ali →
Add permissions → Create inline policy → JSON → paste → save. It is scoped:
ECR and CodeBuild broadly, IAM narrowed to the four role-name prefixes the
toolkit actually creates, S3 to the one CodeBuild source bucket.

`AdministratorAccess` also works and is one click. It is a throwaway hackathon
account, so that is a defensible call — just make it deliberately.

**Re-probe after attaching** (permissions are near-instant but not atomic):

```bash
AWS_PROFILE=panchayat aws ecr get-authorization-token --region us-east-1
```

Then `agentcore deploy` is the whole remaining story.

## Docker is NOT required — do not install it

`agentcore deploy` with no flags builds the **ARM64 image in the cloud with
CodeBuild**. The CLI says so itself: *"No local Docker required (DEFAULT
behavior)."* Confirmed on this machine, which has no container engine — the
toolkit detected that, printed the platform-mismatch warning, and pointed at
the same cloud path.

An earlier draft of this file asked for Docker with buildx. That was wrong and
would have cost a 2GB install for nothing.

    agentcore deploy                → CodeBuild in the cloud   (USE THIS)
    agentcore deploy --local        → run locally, needs Docker
    agentcore deploy --local-build  → build locally, needs Docker

## The contract the image must satisfy

    POST /invocations     the single entrypoint in app.py
    GET  /ping            liveness
    port 8080
    linux/arm64           NOT optional -- see the note in the Dockerfile

## Prerequisites

```bash
pip install bedrock-agentcore-starter-toolkit    # provides the `agentcore` CLI
export AWS_PROFILE=panchayat
```

**On Windows, set this or every command dies:**

```bash
export PYTHONIOENCODING=utf-8
export AGENTCORE_SUPPRESS_RECOMMENDATION=1
```

The CLI prints emoji. Without `PYTHONIOENCODING=utf-8` the Windows cp1252
console throws `UnicodeEncodeError: 'charmap' codec can't encode character
'\U0001f680'` and the traceback looks exactly like a broken install. It is not.
Half an hour was nearly lost to this.

`AGENTCORE_SUPPRESS_RECOMMENDATION=1` silences a deprecation banner. The
toolkit now recommends AWS's newer CLI, `npm install -g @aws/agentcore`. Both
are AWS, both deploy to the same Bedrock AgentCore Runtime; the Python one
works today and is what these steps are verified against. Migrating is a
someday, not a blocker.

## Smoke test the app without a container

Needs no AWS credentials at all:

```bash
PANCHAYAT_BACKEND=memory python app.py
curl localhost:8080/ping
curl -X POST localhost:8080/invocations -H 'Content-Type: application/json' \
  -d '{"household_id":"hh_001","member_id":"mem_001","language":"en",
       "segment":"ward12-4thcross",
       "text":"No water in the tank for three days"}'
```

**`segment` is required.** Without it every report comes back
`unrouted_reason: "no_segment"`. Jurisdiction is looked up by segment
(hard rule 3), `HouseholdPosition` is frozen and carries none, and nothing in
the repo writes a Household row to resolve it from — so it arrives with the
request. This is the defect that made the endpoint look healthy while routing
nothing; see `tests/test_app.py`.

## Configure and deploy

```bash
agentcore configure --entrypoint app.py --name panchayat \
  --deployment-type container --region us-east-1 \
  --requirements-file requirements.txt --disable-memory --non-interactive

agentcore deploy --agent panchayat
agentcore status --agent panchayat
```

`--deployment-type container` is deliberate. The alternative,
`direct_code_deploy`, ships the Python source and never builds our image — so
the arm64 pin, `DOCKER_CONTAINER=1` and the `opentelemetry-instrument` wrapper
would all be silently skipped. Those four settings are the whole reason the
Dockerfile has comments.

`--disable-memory` because `CreateMemory` is **AccessDenied on this account**
(verified 12 Sep — the "contact customer support" flavour, same family as the
Bedrock block). The toolkit degrades gracefully and continues without it, but
it stalls 30–180s first. We keep state in DynamoDB; AgentCore Memory was never
in the design.

### On `configure` overwriting the Dockerfile

An earlier draft warned that the toolkit generates its own `Dockerfile` and
`.dockerignore` and overwrites ours. **Measured 12 Sep: it did not.** It
printed `📄 Using existing Dockerfile`, and `git diff --stat Dockerfile
.dockerignore` came back empty. It copies ours to
`.bedrock_agentcore/panchayat/Dockerfile`, byte-identical.

Check anyway, because it costs nothing and the failure is silent:

```bash
git diff --stat Dockerfile .dockerignore     # must be empty after configure
```

If a future version does overwrite them, port these four by hand — each is
load-bearing and each fails silently: `--platform=linux/arm64`,
`ENV DOCKER_CONTAINER=1`, the `opentelemetry-instrument` wrapper, and `**/.env`
in the ignore file.

## The execution role needs

The toolkit auto-creates the runtime execution role with ECR pull, logs and
the AgentCore trust relationship. **It does not grant DynamoDB.** So after the
first successful deploy, attach `docs/deploy/runtime-table-policy.json` to the
created role or the agent cannot read or write a single case.

**`dynamodb:*Item` is not enough, and the gap is invisible at N=1.** IAM globs
match literally: `*Item` covers `PutItem`/`GetItem`/`UpdateItem`/`DeleteItem`
but **not `TransactWriteItems`** — different word, plural. `core/store.py`
uses transactions in `add_household_to_case`, `split_case` and
`append_consent`, and the request path reaches the first the moment a second
household reports on an existing case. So a role built from a `*Item` glob
deploys clean, serves the single-household demo perfectly, and throws
AccessDenied on the first *merged* case — which is the demo that matters.
The shipped policy lists `TransactWriteItems` explicitly for that reason.

## Which region, and a claim to reconcile

The `panchayat` table is in **us-east-1** (verified 12 Sep: ACTIVE, `GSI1`,
streams `NEW_IMAGE`, 0 items, PAY_PER_REQUEST). `ap-south-1` has no tables.

CLAUDE.md says *"our data stays in ap-south-1, the model calls do not."*
**That is not currently true, and someone will ask.** Two honest options:

- **Move the table to ap-south-1.** It has **0 items**, so today this is free.
  It will not be free later.
- **Update the claim** to say the data plane is us-east-1 for the hackathon.

Either is fine. Shipping the contradiction is not — it is a data-residency
claim in a civic-tech pitch, which is exactly what a judge probes.

## Observability

`opentelemetry-instrument` in the image CMD sets up the SDK; `graph/observability.py`
emits the spans. One `panchayat.request` span per invocation plus one
`panchayat.node.<id>` per node, all carrying `panchayat.case_id`.

Query by `panchayat.case_id` to find the trace, and everything comes with it —
Strands' own `invoke_graph` span sits in the same trace, and so will the model
calls once the account clears. That grouping is why CLAUDE.md puts
observability *before* the trace UI: the UI is a view of it.

With no SDK configured — every `pytest` run, and any local `python app.py` —
the spans are `NonRecordingSpan`: attributes accepted, nothing exported, no
collector contacted. So this costs the offline suite nothing and needs no AWS.

## Known blockers

**Bedrock's model data plane is still blocked account-wide** — re-probed
12 Sep 2026, `us.anthropic.claude-haiku-4-5`: `ValidationException: Operation
not allowed`. Support case 178898467100367.

**This does not block the deploy, and it is now measured rather than assumed.**
Run with live credentials and `PANCHAYAT_MODEL=bedrock`, the request path
completes: routes to BWSSB with a citation, drafts to the Assistant Engineer at
tier 1, sets an SLA deadline — `stubbed_agents: []`, `totalTokens: 0`. The
spine's nodes take an injected model and fall back to deterministic parsing, so
a blocked account costs quality, not availability.

If the account never clears, `core/models.py` is the seam:
`PANCHAYAT_MODEL=anthropic` plus `ANTHROPIC_API_KEY` swaps provider in one
environment variable. Whether that is shipping config or a dev bridge depends
on the hackathon rules — unread, and worth ten minutes.

**The deployed API is write-only.** The entrypoint understands `action:
"health"` and "a household is reporting". There is no way to read a case back —
no get, no list, no approve. A frontend can render the one response it gets and
nothing after. Adding `get_case` / `list_cases` / `approve` to `app.py` is the
next platform task and also closes the signature-capture gap (hard rule 4).

**Nobody else needs AWS credentials.** The suite runs on the memory backend
with no AWS. If you think you need a key, that is a bug in the fakes: say so
in the group.
