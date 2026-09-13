# Deployment acceptance — 13 Sep 2026

**Evidence, captured while the system is up.** Deployments rot; a record of one
working does not. Everything below was produced by querying AWS today, and the
raw command output is reproduced rather than summarised.

Where something is configured but has **not been observed running**, this file
says so. That distinction is the whole point of an acceptance record — see
[§ What is NOT proven](#what-is-not-proven).

---

## The claim we are entitled to make

> **Panchayat is deployed on Amazon Bedrock AgentCore Runtime in `ap-south-2`,
> answering live, with a DynamoDB table and an EventBridge-driven Lambda behind
> it.**

And the one we are **not**:

> ~~Our agents reason using Bedrock models.~~

Model inference is blocked account-wide. Re-probed 13 Sep: every
`bedrock-runtime` invoke returns `ValidationException: Operation not allowed`,
and deployed runs come back at `totalTokens: 0`. Support case 178898467100367.

**Keep these two apart in the video narration.** A judge who opens a trace and
sees zero tokens will notice, and the deployment claim is strong enough on its
own that it does not need the other one propping it up. AgentCore was never
blocked — only the model data plane was.

---

## 1. The Runtime is live

```
arn:aws:bedrock-agentcore:ap-south-2:699073937307:runtime/panchayat-3FFhtr5OfG
```

`get-agent-runtime`, 13 Sep:

```json
{
  "Status": "READY",
  "Version": "5",
  "Created": "2026-09-12T19:48:46.399394+00:00",
  "Updated": "2026-09-12T20:37:26.839734+00:00",
  "Env": {
    "PANCHAYAT_BACKEND": "dynamodb",
    "PANCHAYAT_TABLE": "panchayat",
    "TIME_SCALE": "1",
    "SCHEDULER_ROLE_ARN": "arn:aws:iam::699073937307:role/panchayat-scheduler",
    "WATCHDOG_LAMBDA_ARN": "arn:aws:lambda:ap-south-2:699073937307:function:panchayat-watchdog"
  }
}
```

`TIME_SCALE=1` is worth pointing at: **the deployed system runs on real time.**
The compressed clock is a demo switch and it is not switched on in production.

Deployment type is `direct_code_deploy` — source to S3 to a managed Python 3.12
arm64 runtime. No container, no ECR, and no CodeBuild, which matters because
CodeBuild concurrency is still unapproved on this account.

### It answers today

```
$ aws bedrock-agentcore invoke-agent-runtime  --payload {"action":"health"}
{ "runtimeSessionId": "9b606eec-def6-4fe7-920e-90489f9acd16",
  "contentType": "application/json", "statusCode": 200 }

{"ok": true, "time_scale": "1", "table": "panchayat"}
```

---

## 2. The request path wrote real rows

Verified 12–13 Sep by filing real reports at the live endpoint — not by running a
test. Five cases exist in the table, all routed to **BWSSB at tier 1** with a
seven-day statutory window:

| case_id | status | tier | SLA deadline | authority |
|---|---|---|---|---|
| `case_ea0c49e96c9e` | **dormant** | 1 | 2026-09-19T20:37:48 | BWSSB |
| `case_09d7e10dbf35` | drafted | 1 | 2026-09-19T20:00:11 | BWSSB |
| `case_bd1ee537f17e` | drafted | 1 | 2026-09-19T20:04:46 | BWSSB |
| `case_b96935002f62` | drafted | 1 | 2026-09-19T20:03:08 | BWSSB |
| `case_54454f977bb5` | drafted | 1 | 2026-09-19T19:52:36 | BWSSB |

The table holds **28 rows**, `ACTIVE`, one GSI, streams on
(`NEW_AND_OLD_IMAGES`), across six row types — claim, case, filing, filing
pointer, case-by-feeder, unsigned-filing.

### Hard rule 4 holds on the deployed system

Three filings sit under the `UNSIGNED` partition. One does not:
`case_54454f977bb5`'s filing was approved by `mem_001` through the live
`approve` action, and **a second approval was refused with the original
signatory left intact.**

That is agents-draft-humans-sign, working in production rather than in a test.

---

## 3. The temporal path

Lambda `panchayat-watchdog`, 13 Sep:

```json
{ "Runtime": "python3.12", "Arch": ["arm64"],
  "Handler": "handlers.temporal.handler",
  "Size": 16633981, "State": "Active",
  "Modified": "2026-09-12T20:35:36.062+0000" }
```

Roles: `panchayat-watchdog-exec` (table + logs + `scheduler:CreateSchedule` +
`PassRole`) and `panchayat-scheduler` (trusted by `scheduler.amazonaws.com`
with an `aws:SourceAccount` condition).

### The Runtime books its own wakes

`list-schedules --name-prefix pnc-`:

```json
[ { "Name": "pnc-case_ea0c49e96c9e-expire_draft", "State": "ENABLED" } ]
```

Created by the deployed Runtime, targeted at the Watchdog Lambda, named on the
`pnc-` prefix that `tests/test_deploy_policy.py` pins against the IAM policy,
with `ActionAfterCompletion: DELETE`.

### The Watchdog runs and moves state

Invoking the Lambda with the schedule's own payload returned
`{"woken": 1, "failed": 0}`, and `case_ea0c49e96c9e` moved **`drafted →
dormant`** in DynamoDB — still visible in the table above.

Dormant is the correct destination. Under hard rule 4 an unsigned draft has been
submitted to nobody, so an expired one lapses; it does not breach a statutory
window that no office ever received.

---

## What is NOT proven

**EventBridge has not yet been observed delivering to the Lambda.** The two
halves were verified separately:

- Runtime → EventBridge: the schedule exists, correctly named and correctly
  targeted. ✅
- Lambda → Watchdog → DynamoDB: invoked directly, case transitioned. ✅
- **EventBridge → Lambda, the delivery itself: not observed.** The schedule
  fires 2026-09-19 and we have not waited.

Saying "Runtime → EventBridge → Lambda → Watchdog → DynamoDB works end to end"
overstates it by exactly one hop. The hop is configured, permissioned and
pinned by a test — but configured is not observed, which is the same distinction
this document draws about AgentCore versus model inference.

**Closing it takes two minutes:** create a throwaway schedule firing in ~90
seconds against `panchayat-watchdog` with a real drafted case, and watch the
case transition without anybody invoking anything. `ActionAfterCompletion:
DELETE` cleans it up. Do this before recording.

**Also not proven, and known:**

- The five institution desks are on `localhost:9001–9005`. A cloud runtime
  cannot reach them, so the filing leg — where a ticket reference comes back and
  the statutory clock starts — has not completed in the cloud.
- The ambient path has a handler (`handlers/ambient.py`) but no DynamoDB Streams
  event-source mapping. Streams are enabled and unconsumed.
- There is no authentication on the endpoint.

---

## Reproducing this

```powershell
$env:AWS_PROFILE = 'panchayat'
$R = 'ap-south-2'
$ARN = 'arn:aws:bedrock-agentcore:ap-south-2:699073937307:runtime/panchayat-3FFhtr5OfG'

aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id panchayat-3FFhtr5OfG --region $R
aws dynamodb describe-table --table-name panchayat --region $R
aws lambda get-function-configuration --function-name panchayat-watchdog --region $R
aws scheduler list-schedules --region $R --name-prefix pnc-

$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('{"action":"health"}'))
aws bedrock-agentcore invoke-agent-runtime --agent-runtime-arn $ARN --payload $b64 `
  --region $R --content-type application/json out.json
```

Suite on this commit: **522 passed, 37 skipped, ruff clean.**
