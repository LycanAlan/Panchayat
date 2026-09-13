# What's next — from `main` @ `48e36d9`, 12 Sep

Everything is merged. **416 passed, 37 skipped, 0 failed, ruff clean.**
Every remaining `NotImplementedError` is intentional (an abstract extension
point and the storage seam's by-name stub).

Read this alongside the code review. Every gap below was **verified by
running or grepping it just now**, not recalled.

---

## The shape of the problem

The agents are done. **The system that runs them is half-built, and the demo's
two best moments cannot currently fire outside a test.**

| Execution path | Entry point | State |
|---|---|---|
| Request | `app.py` | code ready, **image never built, nothing deployed** |
| Temporal | `handlers/temporal.py` | ready, **never deployed** |
| Institutions | `institutions/server.py` | the only one that has ever run |
| **Ambient** | **none exists** | streams are on, nothing consumes them |

---

## P0 — the demo does not work without these

### 1. Nothing ever schedules `check_closure` — Raghav + Ali

Grepped every `clock.schedule()` call: **`check_closure` is never scheduled
anywhere.** A desk returning `Outcome.CLOSED` triggers nothing.

`reconcile_closure` is now correct (Raghav fixed it today — a case's own
founding claims no longer dispute it, a neighbour's still does). **It just
never runs in production.** The disputed-closure moment is the peak of the
video and it can only fire from tests and Kartik's harness.

Raghav deliberately did not invent a polling cadence alone, and he was right —
this spans lanes. **Decide the trigger, then it is an hour's work.** Options:
poll open cases on a `check_closure` wake scheduled alongside `check_sla`; or
have the Watchdog schedule one when a filing is submitted.

### 2. No signature capture exists for any tier — Ali

Verified: **nothing anywhere calls `digest.approve()`.** The machinery landed
(`db.sign_filing`, `digest.approve`, `signature_requests`) and nothing invokes
it.

Consequence, exactly as Alakshendra's `build_submit` docstring warns: the
moment the real adapter is installed, **every filing returns `NEEDS_HUMAN`
forever** and no case escalates. Hard rule 4 is enforced and unsatisfiable.

This is the second precondition his note names. The first (a retry wake) is
now met.

### 3. AgentCore deploy — Ali

`Dockerfile`, `.dockerignore` and `docs/DEPLOY.md` exist. **The image has never
been built** (no Docker on this machine) and **the `agentcore` CLI is not
installed** (verified). Nothing is deployed.

`DEPLOY.md` lists which rows are tested and which are not — trust that table.
Known traps recorded there: arm64 is mandatory, `DOCKER_CONTAINER=1` is
load-bearing, `agentcore configure` overwrites our Dockerfile, and
`dynamodb:*Item` does **not** cover `TransactWriteItems`.

---

## P1 — needed for the story to hold up

### 4. Ambient path has no Lambda entry point — Kartik + Ali

`pattern_watch` is implemented, streams are enabled on the table, and **nothing
consumes them.** `handlers/temporal.py` is the model to copy; an
`handlers/ambient.py` is roughly the same shape.

### 5. `stalled_cases()` is memstore-only — Kartik

Verified: `core/store.py` has no `stalled_cases`. So on a real DynamoDB
deploy, `digest.stalled_requests()` catches `NotImplementedError` and returns
`[]` — **"surface it to a human" is still a print statement on the backend we
actually ship.**

### 6. Trace UI — Ali

`demo/` is empty. `graph/trace.py` carries `CaseTrace` and a ContextVar-bound
`record()`, and `graph/observability.py` puts `case_id` on every span, so the
data is all there.

### 7. Cross-case absorption — Kartik + group

When a household's claim is merged into an older case, **its own case stays
alive and can file separately** — a duplicate under hard rule 5, with
provenance `split_case` cannot reconcile. It is emitted and traced loudly now
rather than silently dropped. The fix needs cross-case merge provenance, which
is a group decision.

---

## P2 — grading, and things that bite later

### 8. Blog post and video — Ali

+0.6 on a five-criterion scale, and always the thing that slips. Three moments
for the video: grounded routing with the citation visible, the ambient upgrade,
the disputed closure — **note that the third one cannot fire until P0-1 is
done.** Plus a real ten-minute `RealClock` trace beside the compressed one.

### 9. Devpost submission itself

### 10. A version guard on `Case`

Three writers (`request_path`, `climb()`, ambient `apply_upgrade`), blind
`put_case`. Surfaced independently in three reviews. `escalation_tier` is the
field that will bite first. **One agreed design, not three.**

### 11. `compose_filing()` needs facts nothing collects

25 of 31 curated entries require `rr_number` and nothing captures one. The
recorded decision says it replaces `_draft_filing()`, but wiring it in makes
every escalation refuse. Not a mechanical swap.

### 12. No household registry

`segment` must arrive in the request payload because nothing writes a
Household row. A registry is a `core/types.py` + `core/store.py` change.

### 13. Smaller, verified, unowned

- **No backfill for the new `FILING#` pointer rows** — filings written before
  this commit are invisible to `get_filing`/`sign_filing`, and
  `put_filing_once` cannot self-heal them.
- **`households_per_feeder` is ignored when `geography` is passed**, which is
  the only path the density harness uses. The N=20 column works by the accident
  that 900/9 ≈ 100.
- **TAU across the regime change** — turning embeddings on *stops* pairs
  clustering that cluster today. Sweep `TAU_TOPOLOGICAL` and `TAU_FULL`
  separately and make the trace name which applied.
- **Is Bedrock required as the *model* provider, or just AWS/AgentCore as the
  platform?** Ten minutes of reading, and it decides whether
  `core/models.py`'s Anthropic path is shipping config or a dev bridge.

---

## Suggested split

| Who | Take |
|---|---|
| **Ali** | P0-3 deploy, then P0-2 signature capture, then trace UI, then blog + video |
| **Raghav** | P0-1 `check_closure` trigger — propose the cadence, the group ratifies |
| **Kartik** | P1-5 `stalled_cases` on store, then P1-4 ambient Lambda |
| **Alakshendra** | routing accuracy number, hand `core/tags.py` to platform |
| **Group, 15 min** | the `check_closure` trigger, the `Case` version guard, TAU |

**P0-1 and P0-2 are the two that decide whether the demo shows the product or
shows a router.** Everything else can be narrated.

---

## Two notes on hygiene

- **Branch tips left alone:** `alakshendra/day3-institutions`, `feat/mesh-day3`,
  `feat/hh-closure-evidence`. All three are in `main`; delete them when you are
  ready. Day-1 branches and Ali's are gone.
- **Both canaries were inverted, not deleted.** Alakshendra's now pins that a
  retry wake *is* scheduled; Kartik's pins that a case's own claims are not
  evidence against its closure. Each carries a note about what it used to guard.
