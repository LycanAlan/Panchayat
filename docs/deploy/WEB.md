# The site, deployed

**13 Sep: built, and proven from this machine against the live runtime. Not
deployed yet: one IAM grant stands in the way.**

```
browser ── https://<id>.lambda-url.ap-south-2.on.aws/
             │
             ├─ GET  /*    web/dist, bundled in the zip, SPA fallback to index.html
             └─ POST /api  handlers/web_api.py
                             └─ InvokeAgentRuntime, signed with the Lambda's role
                                  └─ panchayat runtime (app.py)
```

## Why a proxy, and why one Lambda

The runtime takes SigV4 (`authorizer_configuration: null`). A browser has no
AWS credentials and must never be given any, so something with a role has to
sit between the page and `InvokeAgentRuntime`.

One Lambda serves both halves, so the site and the API share an origin and
there is no CORS to configure. It is also the smallest ask: `ali` was refused
`apigateway:GET`, `cloudfront:ListDistributions` and `amplify:ListApps` on
13 Sep, so every service avoided is one fewer grant. S3 + CloudFront is the
better long-term shape and nothing here blocks the move.

## The one step that needs an admin

`lambda:GetFunctionUrlConfig` is denied for `ali`. `CreateFunction` was not
probed, because the probe would have created a function.

Attach **`docs/deploy/web-deployer-policy.json`** to `ali`: IAM → Users →
ali → Add permissions → Create inline policy → JSON. It fits the inline cap.
It is scoped to one function name (`panchayat-web`), one role
(`panchayat-web-exec`), and `PassRole` only to Lambda.

## Deploy

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy_web.ps1
```

It builds the site, bundles `boto3` (the Lambda runtime's copy may predate the
AgentCore data plane), creates or updates the role, the function and a public
URL, then calls `/api` health and prints the URL. It is idempotent, and it
stops at the first `AccessDenied` and names the policy file.

The runtime ARN is read from `.bedrock_agentcore.yaml`, so a redeployed
runtime needs only a rerun.

## Locally

```bash
python scripts/web_api_local.py   # :8787, same handler, your AWS profile
cd web && npm run dev             # :5173, /api proxied to :8787
```

After `npm run build`, http://127.0.0.1:8787 is the production page end to end.

## What was verified, 13 Sep

- `tests/test_web_api.py`, 26 tests. Full suite 565 passed, 37 skipped. ruff
  and oxlint clean, vite build clean.
- The handler on localhost, against the **live** runtime: health ok. A real
  report filed `case_c01e6284febb` in 5 s: routed to BWSSB, drafted to the
  Assistant Engineer at tier 1, read back by `get_case`. A POST with no action
  was refused 400. Client routes fall back to the app; a missing asset is 404.
- Chromium via Playwright at 1440 px and 390 px: report → trace → live file →
  **Sign**. `signed_by` was recorded and the signature queue emptied. No page
  errors, no console errors, no failed requests.
- **Not verified:** the deployed Lambda itself, which does not exist yet, and
  its role path. The same `_invoke` code ran locally under `ali`'s
  credentials.

## What the handler refuses

- **No action, no report.** `app.py` files anything without an action, which
  is right for a trusted caller and wrong for the internet.
- **Allowlisted fields per action.** `case_id` never reaches a report:
  `run_request_path()` would use it, letting a visitor write into someone
  else's case.
- **Strings only, body ≤ 8 KB, text ≤ 2,000 characters.**
- **No botocore retries.** A report mints a case, so a retried read timeout
  would file twice (hard rule 5).
- **Report text is never logged.**

## What it does not do

**Authenticate anyone.** Anyone with the URL can report, read any case whose id
they hold, and sign any draft they can see. The institutions are simulators,
so nothing reaches a real authority. But the Gemini quota and EventBridge
schedules can be spent by strangers. Before sharing the URL widely, consider
reserved concurrency on the function (`lambda:PutFunctionConcurrency`, not in
the policy above).

## What the live page shows honestly, and why

- **Signed filings stay "Submitted: not yet".** Two reasons, both on the
  Watchdog side:
  1. The deployed `panchayat-watchdog` Lambda is from **12 Sep 20:35 UTC**,
     before #34 merged. The runtime books the wake after a signature,
     EventBridge delivers it, and the old code returns early. Measured on two
     browser-signed cases: 749 ms and 5 ms, nothing done.
  2. Even redeployed, submit reaches desks that run only on localhost, and
     returns UNREACHABLE.
- **A lapsed draft is not offered for signing.** The page hides the button on
  `dormant`, `withdrawn` and `resolved` cases. The server still accepts that
  signature (the UNSIGNED bug); the UI covers it, the bug is still there.
- **`/live` lists open cases only**, the `list_cases` limit in
  `graph/read_api.py`.
- **"No model ran" on a one-problem report is true.** `IntakeAgent.parse()`
  asks the model only when a sentence splits into more than one problem
  (`agents/intake.py:79`).
