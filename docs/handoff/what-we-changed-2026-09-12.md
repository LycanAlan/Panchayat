# What we changed — 12 Sep

For Kartik, Alakshendra and Raghav. Written by Ali's session, which has been
covering the household+time and mesh lanes while those two were busy.

**Everything below was verified by running it.** Where a claim is measured, the
number is here. Where something is unverified, it says so.

---

## The state

| | |
|---|---|
| Combined tree, all four PRs merged | **409 passed, 37 skipped** |
| `ruff check .` | clean |
| Failures | **one, and it is the designed signal — see below** |

Four PRs open: **#5** Alakshendra, **#6** platform, **#7** household+time,
**#22** mesh (stacked on Kartik's **#8**, merge it into his branch).

### The one failing test, and the one-line action

`tests/test_submit_adapter.py::test_a_failed_filing_currently_freezes_the_case_permanently`

**Alakshendra — this is yours and it is working exactly as you wrote it.** Your
docstring says:

> *"When the pause path learns to schedule a retry wake and surface to the
> Digest, this test should start failing. That is the signal to delete it."*

PR #7 did that. **Delete the test** (or invert it) when #7 lands. Nothing else
in the tree is red.

---

## The five that would have cost us the demo

Ordered by what they would have destroyed. Three of these were introduced by
this session's own "fixes" and caught by review afterwards.

### 1. Ambient clustering was switched off entirely — self-inflicted

Fixing a duplicate-filing hazard, we made `on_new_claim` bail whenever the
triggering claim was already on a case. But `graph/request_path.py` mints a
fresh `Case` per report, so **every** request-path claim is spoken for by its
own case. Measured end to end: two households on one feeder produced **no
proposal at all**. TAU, the merge path, Anti-Abuse and the entire density
thesis were unreachable, and `eval/density_curve` could not see it because it
calls `apply_upgrade()` directly.

Reverted. **The hazard it was addressing is real and still open** — the source
case stays alive and can file separately (hard rule 5). The fix is for
`cases[0]` to *absorb* the source case, which needs cross-case merge
provenance. That file already says this is a group call. It now emits and
traces the source case id instead of silently dropping the merge.

### 2. We filed against a public body with nobody's approval — self-inflicted

The first Watchdog wake was scheduled at case creation, while the case is
`DRAFTED` — which under hard rule 4 means **submitted to nobody, because
nobody has signed.** `_check_sla` guards only `sla_paused` and the deadline, so
at T+7d it marked the case BREACHED and called `climb()`, which drafted and
**submitted a tier-2 filing to a named officer.** No human anywhere in it, and
the "breach" was of a clock that started before any office received the
complaint.

Two changes, because one of them should not have to be right:
- the request path schedules `expire_draft` — the wake an unsigned draft
  actually needs, which `_expire_unsigned_draft` already guards on. `climb()`
  still schedules `check_sla` once a filing has genuinely landed.
- `_check_sla` refuses to breach a `DRAFTED` case at all.

### 3. The demo-path wake was silently dropped — pre-existing

`VirtualClock.schedule` bound its timer to `asyncio.get_running_loop()`, with a
comment asserting callers always schedule from inside a running loop. They do,
and that was the problem: Strands runs each graph node under `asyncio.run()` on
a thread-pool worker, so the loop **closes the moment the graph returns** and
the timer goes with it. No error, and the trace still said the wake was
scheduled.

Measured under `TIME_SCALE=86400` — the demo configuration — **a filed case
never woke at all.** Now a `threading.Timer`, which has no loop to outlive.
Verified: the wake fires.

### 4. Nothing ever created the first wake — pre-existing

Every `clock.schedule()` in the repo lived inside `climb()`, which is only
reachable *from* a wake. A case opened through `app.py` got a deadline, a
TRACKING line, and no timer. **The Watchdog has 25 passing tests and had never
run in a deployed system.** `handlers/temporal.py` (new) is the EventBridge
entry point that also did not exist.

### 5. The endpoint routed nothing — pre-existing

Found by POSTing a real report at `app.py`: it answered `completed`, returned a
`case_id`, and filed **nothing**, while 279 tests were green. The happy path
only ever worked because the Warden was stubbed and the stub defaulted the
segment to a fixture value.

---

## What changed in *your* files

### Kartik — `agents/pattern_watch.py`, `agents/anti_abuse.py`, `core/store.py`, `eval/`

Your three density-harness findings are all fixed (PR #22, stacked on #8):

- **The N guard checked nothing** — both branches returned the same value.
  Measured: 0 short cases in 18 builds, so latent today, live the first time
  Anti-Abuse refuses a joiner. Your discard-counting addition is in.
- **Only joining claims were written** — and it is worse than you thought:
  **17 of 18 cases had unwritten claims, and one fault with 39 claims put 3 in
  the table.**
- **Table 2 measured nothing.** Verified: `corrected_dispute` returned 0 at
  every N. After fixing #2 it does not become always-True as you predicted —
  it lands at 1/0/3 against the shipped rule's 2/1/3, which proves your actual
  point. **I deleted the table and replaced it with the desk's own oracle.
  Please read that one even if you read nothing else.**

Plus, from review of the rest of your PR:

- **`escalation_requested` could never fire on the memory backend.** `memstore`
  returns the live object, so the emit condition compared a value against
  itself. DynamoDB rebuilds, so it *did* fire there — a backend divergence on
  the event STATUS.md names as the escalation hand-off to `climb()`.
- `_candidates` normalised segments to de-duplicate, then queried with the raw
  string. A case spelled `Ward12-4thCross` retrieved nothing from a street
  stored as `ward12-4thcross` — half a fault, silently.
- `_wrong_feeder` guarded a blank *claim* feeder and left the blank *case*
  feeder open, three lines under your comment *"treating a blank as a match is
  exactly how a decoy gets in."*
- The `case is None` branch discarded `adjudicate()`'s refusals — the one LLM
  call in the lane — so the trace showed "No such case" for a merge the model
  had refused.
- `put_filing_once` handed back the caller's own unwritten filing on a
  cross-case key collision; memstore returned the stored one, so the backends
  disagreed.
- `tau_sweep` raised `ZeroDivisionError` on a corpus with no faults.

### Raghav — `agents/watchdog.py`, `core/clock.py`

PR #7 is in your lane and you did not write it. **Nothing in it is precious.**

- The pause path stopped a case forever: it paused the clock and scheduled
  nothing, and `_check_sla` short-circuits on `sla_paused`. Alakshendra found
  this from the institutions side. It retries now, and surfaces on repeat.
- `climb()` had **three** silent exits; the first pass fixed one. A missing
  jurisdiction entry is transient → pause and leave a wake. Top of the ladder
  is not → ask a person.
- `_retry_submit` guarded only on `sla_paused`, which is never cleared on
  withdrawal — **a withdrawn household's case kept climbing and would have
  filed on their behalf.**
- `RealClock.schedule` now raises `SchedulerNotConfigured` before touching
  boto3. Catch that specific type; catching broadly hides a real outage.
- `"surface it to a human"` was a `print`. `db.stalled_cases()` +
  `digest.stalled_requests()` make it a queue.

### Alakshendra — nothing of yours was edited

Your `build_submit()` docstring is what found defect #4 above. Two asks:
**delete the freeze test** when #7 lands, and note that `compose_filing()`
needs facts nothing collects (below).

---

## Contract changes — these affect your code

1. **`segment` is REQUIRED in the request payload.** Missing it returns
   `unrouted_reason: "no_segment"` and refuses before the graph runs.
2. **`RealClock.schedule()` raises `SchedulerNotConfigured`** when the ARNs are
   unset.
3. **`core/store.py` needs four more functions** (Kartik): `sign_filing`,
   `unsigned_filings`, `get_filing`, `stalled_cases`. Until they land, hard
   rule 4 works on the memory backend and nowhere else.
4. **`ruff==0.16.6` is pinned and `ruff.toml` exists.** `DTZ` is selected, so
   **hard rule 1 is enforced by the linter now.**

---

## Still open — raised, not fixed

- **`compose_filing()` needs facts nothing collects.** 25 of 31 curated entries
  require `rr_number` and nothing captures one, so wiring it in makes every
  escalation refuse. Not a mechanical swap.
- **No household registry**, so `segment` must come from the caller.
- **`stalled_cases()` is memstore-only**, so the stalled queue is empty on
  DynamoDB — the "surface it to a human" fix is still a print on the real
  backend.
- **Cross-case absorption** (see defect #1) — the duplicate-filing hazard.
- **`households_per_feeder` is ignored when `geography` is passed**, which is
  the only path the harness uses. The N=20 column works by the accident that
  900/9 ≈ 100.
- **No backfill for the new `FILING#` pointer rows**, so pre-existing filings
  are invisible to the Digest.
- **A version guard on `Case`** — three writers, blind `put_case`.
- **AgentCore: the image has never been built and nothing is deployed.**
  `docs/DEPLOY.md` says which rows are tested and which are not.
