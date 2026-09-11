# Deploying to Bedrock AgentCore Runtime

Owner: Ali (platform). Read `CLAUDE.md` first.

## What is verified, and what is not

Honesty first, because a runbook that overstates itself is worse than none.

| Step | State |
|---|---|
| `app.py` serves the AgentCore contract | **verified** — started locally, real HTTP |
| `GET /ping` | **verified** — `{"status":"Healthy",...}` |
| `POST /invocations`, health action | **verified** |
| `POST /invocations`, full spine | **verified** — routes, drafts, tracks |
| Two concurrent reports | **verified** — test, no shared `Graph` state |
| `uvicorn` / `starlette` present in the image | **verified** from package metadata, not from a build |
| `docker build` | **NOT verified** — no Docker on the machine this was written on |
| Push to ECR, `agentcore` deploy | **NOT verified** — nothing has been deployed yet |

So: the application contract is tested. The container and the deploy are
written carefully and **have never been run**. Budget for that on the first
attempt, and do it on Tuesday, not Thursday.

## The contract the image must satisfy

    POST /invocations     the single entrypoint in app.py
    GET  /ping            liveness
    port 8080
    linux/arm64           NOT optional -- see the note in the Dockerfile

## Prerequisites

```bash
pip install bedrock-agentcore-starter-toolkit    # the `agentcore` CLI, NOT installed yet
export AWS_PROFILE=panchayat
```

Docker with buildx, for an arm64 image from a non-arm64 machine.

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

## Build and deploy

```bash
docker buildx build --platform linux/arm64 -t panchayat:latest .
agentcore configure --entrypoint app.py
agentcore launch
```

## The execution role needs

- `bedrock:InvokeModel*` on the inference profiles in `core/models.py`
- `dynamodb:*Item`, `Query` on the `panchayat` table and `GSI1`
- `logs:CreateLogStream`, `logs:PutLogEvents`
- ECR pull on the repository the image lands in

## Known blockers

**Bedrock's model data plane is still blocked account-wide** —
`ValidationException: Operation not allowed`, every vendor, every region,
support case 178898467100367. **AgentCore itself is live and was never
blocked**, so the deploy target works. The spine's deterministic nodes
(`warden.minimise`, `remedy.resolve`) never call a model by design, which is
why the verified trace above routes, drafts and tracks on a blocked account.

If the account never clears, `core/models.py` is the seam:
`PANCHAYAT_MODEL=anthropic` plus `ANTHROPIC_API_KEY` swaps provider in one
environment variable. Whether that is shipping config or a dev bridge depends
on the hackathon rules — unread, and worth ten minutes.

**Nobody else needs AWS credentials.** The suite runs on the memory backend
with no AWS. If you think you need a key, that is a bug in the fakes: say so
in the group.
