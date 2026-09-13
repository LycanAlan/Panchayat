# Status — 13 Sep, evening

Four PRs merged today (#34–#37). **`main` at `6675aa6`, 539 passed, 37 skipped,
ruff clean. Runtime version 10, READY, reasoning on Gemini.**

The headline: **the deployed system now reasons, and the signature deadlock is
fixed in code.** Both were broken this morning and neither was visible.
**Correction, later the same evening:** the deadlock fix is only half deployed.
The watchdog Lambda was never redeployed. See *The site, and the deploy gap it
found*.

---

## What changed

### The signature deadlock (#34) — the big one

A household could report, get a letter drafted to a named officer, and sign it,
and **nothing happened, ever.** The case sat at DRAFTED forever: never
submitted, never tracked, never escalated.

Two faults. Nothing booked a wake on signature — `expire_draft`'s handler
returns the moment it sees a signature, correctly, since its job is expiring
*unsigned* drafts. And `climb()` read `escalation_tier + 1` unconditionally,
so merely delivering a wake would have filed **tier 2** and orphaned the
tier-1 letter the household actually signed.

Why 522 tests missed it: `climb()` is the only thing that books a `check_sla`
wake, and a `check_sla` wake is the only thing that reaches `climb()`. **A
starter motor wired to run only once the engine is already turning.** Every
test calls `climb()` directly. `tests/test_signature_to_filing.py` deliberately
never does.

### Gemini on the model seam (#35)

**The institutional tail had never run — anywhere.** Each desk is
`Agent(model=get_model("cheap"))` with four tools, Bedrock is blocked, and
`tests/test_institutions.py` exercises the deterministic `InstitutionDesk`
underneath rather than the agent that answers over A2A. "Film the filing leg
locally" was never an option either.

`PANCHAYAT_MODEL=gemini` is now the third provider. Free tier, and unlike
Anthropic **Google serves embeddings** — so `semantic_available` can stop being
a permanent caveat once `core/scoring.py` routes through the seam instead of
calling Bedrock Titan directly. **That is Kartik's file and his call.**

Four filings through the real `bwssb` profile:

```
REJECTED: reference number does not match our records
ACCEPTED BWSSB-100001: sla_days=7
ACCEPTED BWSSB-100002: sla_days=7
UNREACHABLE: portal not responding
```

Calibrated behaviour, real ticket references. First time that tail has executed.

### Intake wired, and the tokens told the truth (#36, #37)

Gemini went live and the trace still said `totalTokens: 0` — twice, for two
different reasons.

First: `_intake` used the module-level `intake.parse()`, whose default instance
has no model. The provider was live and unreachable from the one node that
wanted it. Now adapted, behind an **explicit gate** — `PANCHAYAT_MODEL` set and
that provider's credential present. The naive check ("can I build a model?") is
true everywhere, because `BedrockModel(...)` constructs fine with no
credentials and only fails when called; it would have put a live network call
in every offline test run.

Second: the adapter's Agent is not a Graph node, so its metrics never reached
`accumulated_usage`. The model *was* running and we were reporting zero. We
have been careful all build to say when a model did **not** run; reporting zero
for one that did is the same dishonesty pointing the other way.

Live now: `{"inputTokens": 47, "outputTokens": 23, "totalTokens": 70}`.

A one-problem report still shows `totalTokens: 0`, and that is correct:
`IntakeAgent.parse()` asks the model only when a sentence splits into more
than one problem (`agents/intake.py:79`).

---

## The site, and the deploy gap it found

Kartik's site (`web/`) rendered fixtures only; nothing fetched. On
`feat/plat-web-live` it is connected. The intake line files a real report and
replays the runtime's trace, and `/live/:caseId` reads the case back and takes
the signature. `handlers/web_api.py` is one Lambda that serves the build and
forwards `POST /api`, because a browser cannot sign SigV4 and `ali` is refused
CloudFront, API Gateway and Amplify. Details: `docs/deploy/WEB.md`.

**Not deployed.** `lambda:GetFunctionUrlConfig` is denied for `ali`, so an
admin has to attach `docs/deploy/web-deployer-policy.json` first. Everything
else was proven from this machine against the live runtime, including in
Chromium: report, trace, live file, signature recorded.

**And signing through it showed that #34 is only half deployed.** Two filings
signed from the browser at 16:17–16:18 UTC booked their `retry_submit` wakes.
EventBridge delivered both, and the watchdog Lambda returned in 749 ms and
5 ms having done nothing. Both cases are still `drafted`, unsubmitted, with
`sla_paused=false`. The Lambda's code is from **12 Sep 20:35 UTC**, and #34
merged 13 Sep 11:41 UTC. The package was downloaded and checked: it has no
`_tier_to_work`. The runtime half (approve books the wake) is live; the
Watchdog half that acts on it is not. Rebuild per `docs/deploy/SETUP.md`
Stage 2 and `update-function-code`.

Even then a filing will not reach a desk. The desks still run only on
localhost, so submit returns UNREACHABLE and the case pauses and retries. That
is the designed path, and it is the next wall.

---

## Deploy gotchas, both found the hard way

**`agentcore launch` wipes every environment variable unless you pass `-env`
for all of them.** Version 6 went out with `Env: null`, silently fell back to
`PANCHAYAT_BACKEND=memory`, accepted reports, returned real-looking case ids
and **wrote nothing to DynamoDB.**

Worse, `health` still answered `{"ok": true, "table": "panchayat"}`, because
those are `os.environ.get(..., default)` values rather than reads of live
config. **The health check cannot tell a configured system from an
unconfigured one.** Caught only by querying the table directly.

The full incantation, every time:

```powershell
$env:PATH = "$root\.venv\Scripts;$root\scripts;$env:PATH"   # uv + the zip shim
$key = (Get-Content .env | ? { $_ -like 'GEMINI_API_KEY=*' }) -replace '^GEMINI_API_KEY=',''
agentcore launch `
  -env PANCHAYAT_BACKEND=dynamodb -env PANCHAYAT_TABLE=panchayat -env TIME_SCALE=1 `
  -env WATCHDOG_LAMBDA_ARN=... -env SCHEDULER_ROLE_ARN=... `
  -env PANCHAYAT_MODEL=gemini -env "GEMINI_API_KEY=$key"
```

`uv.exe` and `scripts/zip.cmd` both have to be on PATH or launch refuses.

**`gemini-2.5-flash` is dead for new keys** — 404, "no longer available to new
users, use `models/gemini-3.6-flash`". The Claude 3.5 trap, second vendor. Only
caught because the smoke test *called* the model rather than reading about it.
`test_no_end_of_life_model_ids_anywhere` now refuses any `gemini-2.x`.

---

## Where it stands

| | |
|---|---|
| Runtime | v10 READY, ap-south-2, Gemini, real tokens |
| Request path | live, reasoning, persisting |
| Temporal path | live, EventBridge delivery **observed** |
| Signature → submit | **half deployed**: the runtime books the wake, but the watchdog Lambda runs 12 Sep code and ignores it |
| Institution desks | still localhost, the last wall |
| Ambient / clustering | **cannot fire in production** |
| Site | connected and proven locally against the live runtime; **not deployed**, needs one IAM grant |

## Next, in order

1. **Redeploy the watchdog Lambda.** It is the missing half of #34, and
   without it no signed filing is ever attempted. Rebuild the Stage 2 package
   from `main` and `update-function-code`.
2. **Deploy the site.** An admin attaches
   `docs/deploy/web-deployer-policy.json` to `ali`, then run
   `scripts/deploy_web.ps1`.
3. **Deploy the five desks.** AgentCore `serverProtocol` accepts `A2A`
   natively — checked, `['MCP', 'HTTP', 'A2A', 'AGUI']` — so they can be
   AgentCore runtimes on the same `direct_code_deploy` path, and we have quota
   in ap-south-2. One snag: `serve()` binds `profile.port` (9001–9005) and
   AgentCore wants 8080; the host is env-overridable and the port is not.
   Name them `panchayat-sim-*` and say "simulated counterparty" every time —
   an unlabelled `bwssb` on our account is a worse credibility problem than
   localhost ever was.
4. **Ambient event-source mapping.** The package is built (47.1 MB zipped,
   arm64, py3.12) but **nothing is deployed and no mapping exists** — verified
   zero. Clustering, the thesis of this project, still cannot fire in
   production. `handlers/ambient.py` is ready and the stream is on.
5. **The `UNSIGNED` bug**, still unowned. A DORMANT case keeps its filing in
   the signature queue, so the Digest will ask a person to sign paper for a
   complaint that already lapsed — and `approve()` would accept it, because it
   validates the filing and never the case. The site hides the button on a
   lapsed case; the server is unchanged.
6. **No authentication**, still P1, and worse the day the site has a public
   URL: anyone holding it can report, read a case by id, and sign.

## Two loose ends

**The Gemini key is in `.env`** (UTF-8; PowerShell wrote it as UTF-16 first and
`python-dotenv` cannot read that). It is a free-tier key with no billing, so
Ali's call not to rotate it is reasonable — revisit the day billing is attached
to that Google Cloud project. It is deployed as a plain runtime env var;
`.bedrock_agentcore.yaml` has `api_key_credential_provider_name` sitting null
for AgentCore Identity, which needs `get_model()` to become async.

**`test_seven_virtual_days_fire_in_seven_real_seconds` is flaky.** Its polling
ceiling and its upper assertion bound are both `9.0`, so on a loaded machine
the loop times out and it fails as though the compressed clock were broken.
It failed once today and passed alone. `core/clock.py` is Raghav's.
