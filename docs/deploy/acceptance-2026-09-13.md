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

| case_id | status | tier | SLA deadline | how it got there |
|---|---|---|---|---|
| `case_ea0c49e96c9e` | **dormant** | 1 | 2026-09-19T20:37:48 | Lambda invoked directly (12 Sep) |
| `case_09d7e10dbf35` | **dormant** | 1 | 2026-09-19T20:00:11 | **EventBridge delivered it** (§3.1) |
| `case_bd1ee537f17e` | drafted | 1 | 2026-09-19T20:04:46 | awaiting a signature |
| `case_b96935002f62` | drafted | 1 | 2026-09-19T20:03:08 | awaiting a signature |
| `case_54454f977bb5` | drafted | 1 | 2026-09-19T19:52:36 | **signed** by `mem_001` |

The two dormant cases are the interesting ones, and they are dormant for
different reasons: the first was moved by invoking the Lambda by hand, the
second by EventBridge firing on its own. Keeping both distinguishes what we
configured from what we watched happen.

The table holds **28 rows**, `ACTIVE`, one GSI, streams on
(`NEW_AND_OLD_IMAGES`), across six row types — claim, case, filing, filing
pointer, case-by-feeder, unsigned-filing.

### Hard rule 4 holds on the deployed system

Five filings exist. **Two carry a signature** — `mem_001` on
`case_54454f977bb5` and `mem_final` on `case_bd1ee537f17e`, both recorded
through the live `approve` action. The other three sit in the `UNSIGNED`
partition, and the queue contains exactly those three and nothing else.

Approving `case_54454f977bb5` a second time was **refused, with the original
signatory left intact.**

That is agents-draft-humans-sign, working in production rather than in a test.

### A finding this run produced

`case_09d7e10dbf35` is now **DORMANT**, which `agents/watchdog.py:37` treats as
terminal — and its filing is **still sitting in the `UNSIGNED` queue.**

Neither `store.unsigned_filings()` nor `digest.signature_requests()` checks the
case's status, so the Digest will keep asking a named person to sign paper for a
complaint that has already lapsed. Worse, `approve()` would accept it: it
validates the filing, never the case, so you can sign a terminal case's draft
and nothing refuses you.

That is a small bug with an outsized cost, because it lands on the one rule the
whole product's credibility rests on. Being asked to take personal liability for
a dead complaint is exactly the kind of thing that makes a household stop
trusting the tool.

Not fixed here — this file is a record, not a change. The clean fix is one
guard in `agents/digest.py::signature_requests()` (Ali's file) plus the same
filter on the unscoped queue in `core/store.py` and `core/memstore.py`
(Kartik's), with parity tests on both backends.

**Worth noting how it was found:** not by reading the code, which several of us
have, but by running the deployed system and then reading what the table
actually said afterwards. It is the only defect on this page that no test
caught.

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

### 3.1 EventBridge delivering to the Lambda — **observed**

This is the hop that was missing, and it is worth being explicit about why.
Until 09:30 UTC today the chain had only been verified in two halves: the
Runtime created a schedule (verified), and the Lambda ran the Watchdog and
moved a case (verified — **by invoking the Lambda directly**). EventBridge
actually delivering had never been seen, because the only real schedule fires
on the 19th.

Configured, permissioned and pinned by a test is not the same as observed. So
it was observed.

A schedule was created for a genuinely drafted case, `case_09d7e10dbf35`, to
fire two minutes out, and then **nothing was invoked by hand** — the table was
polled until it changed on its own:

```
09:27:37  status=drafted  schedules_remaining=1
09:28:00  status=drafted  schedules_remaining=1
   ...
09:29:54  status=drafted  schedules_remaining=1     <- fire time 09:29:19
09:30:17  status=dormant  schedules_remaining=0
```

CloudWatch, `/aws/lambda/panchayat-watchdog`:

```
INIT_START Runtime Version: python:3.12.mainlinev2.v34
START RequestId: 026aa66c-ef4f-4633-8a8d-614deb644e34

DORMANT     watchdog    -> draft expired unsigned after 7 days -- one notice

REPORT  Duration: 977.68 ms  Billed: 1629 ms
        Memory Size: 512 MB  Max Memory Used: 120 MB
        Init Duration: 650.91 ms
```

Three things land at once here. **EventBridge invoked the Lambda on its own
schedule.** The Watchdog emitted a real trace line in the format the demo
surface renders. And `schedules_remaining=0` means `ActionAfterCompletion:
DELETE` worked — the schedule cleaned itself up, so a case that has been
handled leaves nothing behind to fire twice.

Cold start was 651 ms and the whole wake cost 977 ms against a 512 MB / 60 s
allocation, using 120 MB. The temporal path is comfortably inside its budget.

**So the full chain is now observed, not inferred:**

```
Runtime → EventBridge Scheduler → Lambda → Watchdog → DynamoDB
```

---

## What is NOT proven

**Not proven, and known:**

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
