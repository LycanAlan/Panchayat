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
- After the review fixes, against the live runtime on `case_ece3850e1406`:
  approve with no household → 400, as a stranger household → 403, on the
  dormant `case_09d7e10dbf35` → 409, as the owner → 200 signed. In Chromium
  the owner still signs cleanly, and an empty field cannot be submitted.
- **Not verified:** the deployed Lambda itself, which does not exist yet, and
  its role path. The same `_invoke` code ran locally under `ali`'s
  credentials.

## What the handler refuses

- **No action, no report.** `app.py` files anything without an action, which
  is right for a trusted caller and wrong for the internet.
- **Allowlisted fields per action.** `case_id` never reaches a report:
  `run_request_path()` would use it, letting a visitor write into someone
  else's case.
- **A signature only from the chosen household, only on a live case.** Before
  forwarding `approve`, the door calls `get_case` with the browser's household
  id. It forwards only if that filing is waiting with `yours: true` and the
  case is not `dormant`, `withdrawn` or `resolved`. The runtime's `approve`
  checks neither. Reproduced on 13 Sep before the check existed: a request
  carrying only a case id signed `case_c01e6284febb` as
  `mem_stranger_review`.
- **Strings only, body ≤ 8 KB, text ≤ 2,000 characters.** An empty field
  sends nothing; the placeholder is never filed.
- **No botocore retries, and timeouts that fit.** A report mints a case, so a
  retried read timeout would file twice (hard rule 5). Connect 3 s + read
  55 s, twice for an approve, stays under the 120 s Lambda. botocore's default
  connect timeout alone is 60 s. When a call times out, the page says the
  report *may* have landed instead of inviting a second one.
- **Report text is never logged.**

## What it does not do

**Authenticate anyone.** There is no login. The household id stands in: it is
minted at random in the reporter's browser and no read action returns it. A
case id lets you read that case, including the draft text. Signing it also
takes the household id. That is a bearer token, not an identity. The
institutions are simulators, so nothing reaches a real authority.

**Throttle anyone.** This account's Lambda concurrency limit is **10**
(`get-account-settings`, 13 Sep), so reserved concurrency cannot be set at
all. Those 10 are shared with `panchayat-watchdog`. A flood of reports on the
site delays Watchdog wakes; EventBridge Scheduler retries them, so they come
late rather than never. A quota increase is the real fix, and it needs
someone with Service Quotas access.

## What the live page shows honestly, and why

- **Signed filings stay "Submitted: not yet".** Two reasons, both on the
  Watchdog side:
  1. The deployed `panchayat-watchdog` Lambda is from **12 Sep 20:35 UTC**,
     before #34 merged. The runtime books the wake after a signature,
     EventBridge delivers it, and the old code returns early. Measured on two
     browser-signed cases: 749 ms and 5 ms, nothing done.
  2. Even redeployed, submit reaches desks that run only on localhost, and
     returns UNREACHABLE.
- **A lapsed draft cannot be signed through the site.** The page hides the
  button on `dormant`, `withdrawn` and `resolved` cases, and the door refuses
  the request with 409. The runtime's `approve()` still accepts it from any
  caller with AWS credentials (the UNSIGNED bug). The bug is fenced off, not
  fixed.
- **`/live` lists open cases only**, the `list_cases` limit in
  `graph/read_api.py`.
- **"No model ran" on a one-problem report is true.** `IntakeAgent.parse()`
  asks the model only when a sentence splits into more than one problem
  (`agents/intake.py:79`).
