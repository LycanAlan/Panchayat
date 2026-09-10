# Raghav — 2-Day Execution Plan

> **Start your VS Code Claude session with exactly this:**
> *"Read `docs/team/RAGHAV-PLAN.md`. Do not read other files until it tells you
> to. Start at Block 0 and work in order."*

This plan compresses the 4-day brief in `docs/team/RAGHAV.md` into 2 days. It is
written so an agent can execute it **without exploring the repo** — every
signature, rule and trap is stated here. Do not re-derive things.

**Current as of commit `fa7ff91` ("Break the cross-lane dependencies so nobody
idles").** That commit shipped `core/db.py`, `core/memstore.py`, `core/fakes.py`,
`data/jurisdiction/ward12.sample.yaml`, `tests/conftest.py` and
`tests/test_contract.py`. Decision **D2 below was rewritten because of it** —
you no longer monkeypatch anything. If `git log -1` shows something newer than
`fa7ff91`, re-check D2 and T7 before trusting this plan.

**Do not edit files outside Raghav's lane:**
`core/clock.py`, `agents/intake.py`, `agents/household.py`, `agents/warden.py`,
`agents/watchdog.py`, plus new files under `tests/`.

## Branch discipline — never commit to `main`

All of this work happens on **`feat/household-time`**. `main` is reviewed and
merged by the group together, deliberately, later. Nothing lands there from this
session.

```bash
git branch --show-current      # must print feat/household-time, every time
```

The `.githooks/pre-commit` guard enforces this and **it genuinely fires** — it
blocks direct commits to `main`, refuses AWS keys, and refuses `.env`. Enable it
once per machine with `scripts/setup-hooks.ps1`.

> **Never use `git commit --no-verify` to get past it.** If the hook blocks you,
> it has found something real. Fix the cause, or raise it in the group.

Commit in small, reviewable steps — one commit per block in this plan, so the
group can review the lane as a sequence rather than one wall of diff. Do not
merge, rebase onto, or push `main`.

---

## Context you need (do not go looking for it)

**The system:** a neighbourhood agent mesh. Households report service failures;
the mesh files against the right authority, tracks the statutory clock, notices
breaches and climbs to the next tier. We pursue resolution — never write
"solves". Context is Bengaluru, Ward 12.

**Raghav's lane:** everything left of the privacy membrane, plus time itself.

**The four hard rules that govern this lane:**

1. Nothing calls `datetime.utcnow()` outside `core/clock.py` and `core/types.py`.
   Take time from `core.clock.get_clock()`.
2. `HouseholdPosition` **never** crosses the membrane. Only `Claim` does, and
   only `warden.minimise()` emits one.
3. Agents draft, humans sign. Tier 4 drafts an RTI and supplies **no** name,
   address or ₹10 fee.
4. Every institutional action is idempotent — use `core.db.put_filing_once()`.

**Frozen contracts** live in `core/types.py`. Read that file once at Block 0 and
do not edit it. The dataclasses you need: `MemberContext`, `HouseholdPosition`,
`Claim`, `ConsentGrant`, `ConsentScope`, `Case`, `CaseStatus`, `Filing`,
`JurisdictionEntry`, `EscalationStep`, `Service`, `Priority`, `Tail`.

---

## Decisions already made — do not re-open these

| # | Question | Ruling |
|---|---|---|
| D1 | RTI escalation tier — 3 or 4? | **Tier 4.** `docs/team/RAGHAV.md` and Alakshendra's ladder YAML both say 4. The `Tier 3` in the `climb()` docstring is stale — **fix that docstring** (it is in your file). |
| D2 | `core/store.py` and `data/jurisdiction/` are stubs in other lanes | **SUPERSEDED by commit `fa7ff91`** — the fakes now exist. Import storage from **`core.db`** (never `core.store` or `core.memstore`). Build domain objects with **`core/fakes.py`**. Read the ladder from **`data/jurisdiction/ward12.sample.yaml`**. Use the `clock` and `outage` fixtures in `tests/conftest.py`. **Do not monkeypatch, do not build fixtures inline.** |
| D3 | Bedrock model calls | Every LLM call goes through an **injectable `model` parameter defaulting to the Bedrock id in env**. Tests inject a deterministic fake, so the suite runs with **no AWS credentials**. `CLAUDE.md` now confirms **Bedrock authorization is still pending on the account** — so this is mandatory, not a nicety. Day 1 needs no model at all. |
| D4 | `datetime.utcnow()` in frozen `core/types.py:73` | **Exempt it.** It is documented as dataclass defaults only, and `types.py` is frozen (hard rule 10). Your grep check excludes `core/types.py` and `core/clock.py`. |

---

## Six traps found in the current repo. Read these before writing code.

**T1 — naive vs aware datetimes. This one will silently corrupt the demo.**
`core/types.py` defaults (`Claim.created_at`, `ConsentGrant.granted_at`) are
**naive** UTC. If your clock ever returns a timezone-aware datetime, every
comparison against a frozen default raises
`TypeError: can't compare offset-naive and offset-aware datetimes` —
including `ConsentGrant.is_live()`, which the Warden calls.

> **Rule: `Clock.now()` must return a NAIVE UTC datetime, always.**
> Use `datetime.now(timezone.utc).replace(tzinfo=None)`.
> That is deprecation-free on Python 3.13 **and** naive. Never return `tzinfo`.

**T2 — `VirtualClock.schedule()` is broken as written.**
[core/clock.py:121](../../core/clock.py) calls `asyncio.get_event_loop()`. On
Python 3.13 that emits a `DeprecationWarning` when no loop is running, and
`loop.call_later` only fires while a loop is actually running — so the timer
never fires from a plain sync test. Fix: use `asyncio.get_running_loop()` and
call `schedule()` from inside a running loop. Tests wrap in `asyncio.run(...)`.

**T3 — the test suite only imports from one directory.**
`tests/conftest.py` now exists and does `from core import fakes, memstore`. That
resolves **only because `python -m pytest` puts the current directory on
`sys.path`**. Verified: running it with any other working directory gives
`ModuleNotFoundError: No module named 'core'`, and a venv's bare `pytest`
console script does not add cwd either.

> **Always run `python -m pytest` from the repo root.** Never bare `pytest`.

The durable fix is a `pyproject.toml` with `[tool.pytest.ini_options]
pythonpath = ["."]`, or an empty `conftest.py` at the repo root. That is shared
plumbing — **raise it with Ali, do not add it unilaterally.**

**T4 — `Swarm(max_iterations=...)` is unverified.**
`CLAUDE.md`'s verified snippet lists `entry_point`, `max_handoffs`,
`execution_timeout`, `node_timeout` — **no `max_iterations`**. Your brief and the
stub docstring both include it. Before using it, run:
```python
import inspect; from strands.multiagent import Swarm; print(inspect.signature(Swarm.__init__))
```
Pass `max_iterations` **only if it is in that signature.** Do not guess.

**T5 — `watchdog(case_id, action)` has no defined action vocabulary.**
Nothing in the repo defines the legal values of `action`, but Ali's Lambda will
dispatch on them and `RealClock.schedule()` builds an EventBridge schedule name
as `"pnc-" + case_id + "-" + action`. So actions must be
`[0-9a-zA-Z-_.]` only. **You define this set and announce it to the group:**
`check_sla`, `check_closure`, `expire_draft`. No others.

**T6 — `Claim` has no resolution flag.**
`reconcile_closure()` needs "still live". There is no `resolved` field on
`Claim` and `core/types.py` is frozen. Define liveness as *claims in the
segment+service window that postdate the closure timestamp*, and leave a
one-line hook where a future resolution signal would filter. Do not add fields.

**T7 — `main` is red right now, and the failure is in your lane.**
`python -m pytest` on commit `fa7ff91` gives **6 passed, 1 failed**:

```
FAILED tests/test_contract.py::test_virtual_clock_compresses_a_statutory_week
assert (deadline - clock.now()).days == 7   ->   assert 6 == 7
```

**The clock is not broken — the assertion is.** `timedelta.days` truncates
toward zero, so the instant any real time elapses between `start = clock.now()`
and the comparison, 7 days becomes `6 days, 23:59:58`, and `.days` is `6`. It
would fail with a perfect clock. Fix the assertion, not `core/clock.py`:

```python
remaining = (deadline - clock.now()).total_seconds() / 86400.0
assert 6.9 < remaining <= 7.0
```

`tests/test_contract.py` is shared, not yours — but the test asserts on **your**
contract, so post the one-line fix in the group rather than editing silently.
Getting the suite green is Block 1's first action.

**T8 — `case.escalation_tier` has two writers and no locking. Raise this in the
group on Day 1; do not quietly pick a rule.**

Kartik's `apply_upgrade()` (ambient, fired by DynamoDB Streams) is specified to
*"raise the escalation tier"*. Your `climb()` (temporal, fired by EventBridge)
is specified to *"advance one escalation tier"*. Two independent triggers
read-modify-write the same field, and `put_case()` is a blind overwrite —
`memstore.py` is literally `_cases[case.case_id] = case`, and a DynamoDB
`PutItem` will behave the same.

Two failure modes, both bad:
- **lost update** — an escalation silently doesn't happen, and the SLA clock
  runs against a tier nobody filed at
- **double escalation** — the tier jumps 1 → 3, skipping a statutory authority.
  That is not a cosmetic bug: it files at the wrong body, which is *the exact
  failure this project claims to fix.*

Propose one of: `climb()` is the only writer and `apply_upgrade` requests an
escalation rather than performing one; or `put_case` grows a conditional write
on a version attribute. **This is a decision for the group, not for you alone**
— it needs Kartik's agreement and it belongs in the STATUS.md decisions log.
The same hazard applies to `sla_deadline` and `sla_paused`.

**T9 — `reconcile_closure()` has no closure timestamp to read.**
`Case` has no `closed_at`, `Filing` has no closure time (only `submitted_at`),
`Filing.response` is a bare string, and `core/types.py` is frozen so you cannot
add one. Resolve it without touching the contract: the Watchdog is **woken** by
the `check_closure` action, so treat **`clock.now()` at that wake** as the
observation moment, and dispute using claims live at that instant. Write the
assumption in a one-line comment so the reviewer sees it was chosen, not missed.

**T10 — half of `core.db` can be `None` at runtime.**
`core/db.py` re-exports `get_claim`, `open_cases`, `revoke_consent`,
`filings_for_case` and `reset` via `getattr(_impl, ..., None)`, so a
partially-built DynamoDB backend does not break everyone's imports. They exist
on `memstore` and are **optional on `store`**. If you call
`db.filings_for_case(...)` it works all day on memory and raises
`TypeError: 'NoneType' object is not callable` the first time anyone runs
`PANCHAYAT_BACKEND=dynamodb`.

Prefer the twelve guaranteed functions. If you genuinely need an optional one,
guard it **and tell Kartik it is now required** so it lands in his `store.py`.

**T11 — `watchdog()` takes no clock, so tests cannot control time.**
`climb(case_id, clock)` receives a clock; `watchdog(case_id, action)` does not,
and Ali's Lambda calls the two-argument form. Give it a default instead of
changing the call shape:

```python
def watchdog(case_id: str, action: str, clock: Clock | None = None) -> None:
    clock = clock or get_clock()
```
Additive, your own file, Ali's existing call still works, and your tests can now
pass the `clock` fixture in.

---

# DAY 1 — Time, the membrane, and the peak

Everything on Day 1 is **deterministic**: no model calls, no AWS, no network.
The whole day is provable offline. That is deliberate — it front-loads every
item on the definition-of-done checklist that carries proof for the video.

### Block 0 — Environment (do this first, ~20 min)

```powershell
git pull                      # you need commit fa7ff91, it ships the fakes
.\scripts\verify-setup.ps1
```
That script creates the venv, installs `requirements.txt`, and — importantly —
probes an **actual Bedrock invoke**, because listing models does not prove you
can call them.

**Bedrock authorization is still pending on the account**, so expect that probe
to fail. **Keep going.** Per D3 nothing on Day 1 and nothing in the test suite
needs a model. The default `PANCHAYAT_BACKEND=memory` means the whole system
runs offline.

Confirm the baseline before you write anything:
```bash
python -m pytest -q          # expect 6 passed, 1 failed (trap T7)
```

Read `core/types.py`, `core/db.py` and `core/fakes.py` once now. Do not read
them again — the parts you need are quoted throughout this plan.

### Block 1 — `core/clock.py`

Fix, do not rewrite. The file is already ~90% correct.

0. **Get `main` green first (trap T7).** Post the one-line assertion fix for
   `test_virtual_clock_compresses_a_statutory_week` in the group. Nothing else
   you do today is trustworthy while the suite is red.
1. Apply **T1**: add a module-level `_utcnow()` returning
   `datetime.now(timezone.utc).replace(tzinfo=None)`. Use it in
   `RealClock.now()` and `VirtualClock.__init__`/`now()`. Naive UTC, always.
   `core/fakes.py` uses `T0 = datetime(2026, 9, 7, 21, 40)` — **naive**, which
   confirms the ruling. An aware clock breaks every fake in the repo.
2. Apply **T2**: `VirtualClock.schedule()` uses `asyncio.get_running_loop()`.
3. Leave `get_clock()` as the only place `TIME_SCALE` is read.
4. Do **not** add a `demo_mode` flag anywhere.

`tests/conftest.py` already gives you a `clock` fixture: a `VirtualClock` at
`scale=86400`, `epoch=fakes.T0`, with an `on_fire` callback recording into
`clock.fired`. **Use it. Do not build your own VirtualClock in tests.**

**`tests/test_clock.py` — this is your proof for the video:**

```python
def test_seven_virtual_days_fire_in_seven_real_seconds():
    # VirtualClock(scale=86400) -> one statutory day per real second
    # schedule 7 virtual days out, assert the callback fires in ~7 real seconds
    # tolerance: 6.0 < elapsed < 9.0
```
Use the injected `on_fire` callback so the test never imports `agents.watchdog`.
Wrap the body in `asyncio.run(...)`.

Add faster unit tests alongside it (`scale=8640000`) for the edge cases:
`cancel()` stops a pending fire; a past `at` fires immediately (`real_delay`
clamps to 0); `now()` advances monotonically.

### Block 2 — `agents/warden.py` → `minimise()`

**This is most of the value in the lane and it must work.** Pure function, no
model, no store. Signature is frozen by the stub:
`minimise(position: HouseholdPosition) -> Claim`.

The reductions, exactly:

| In (`HouseholdPosition`) | Out (`Claim`) |
|---|---|
| `budget_ceiling_inr=500` | `has_budget_ceiling=True` — **the integer never appears** |
| `deadline_reason="dialysis prep"` | `priority=HIGH` (or `URGENT`), `reason_withheld=True` — **the string never appears** |
| `hard_deadline` | may inform `priority`; do not copy the reason |
| `contributing_members`, `raw_report`, `summary` | **must not** be copied verbatim into `description` |
| `household_id` | opaque id only |

`description` is minimised free text with **no names**. `Claim.observed_since`
may carry timing. Everything else stays inside the membrane.

**We promise minimisation, not anonymity.** Eight houses on a cross street means
any claim precise enough to file is precise enough to identify. Never write
"anonymous" in code, comments or docstrings. What we guarantee is that
**income, health, arrears and schooling never cross.**

**`tests/test_warden.py` — test this adversarially, not happily.**
`fakes.a_household_position()` is **built for exactly this test** and already
carries `budget_ceiling_inr=500`, `deadline_reason="dialysis prep"`, a
`hard_deadline` of `T0 + 8h` and a Kannada `raw_report`. Use it, then assert on
the **serialised claim** (`to_dict(claim)` from `core.types`, flattened to one
string): the digits `500`, the substring `dialysis`, and every member name are
**absent**. Assert `has_budget_ceiling is True` and `reason_withheld is True`.

Also assert the return type is `Claim` and that no `HouseholdPosition` field
name survives in the output dict.

### Block 3 — `agents/warden.py` → `consent_covers()`

`consent_covers(grants, scope, service, now) -> tuple[bool, str]`

Scope-drift check. A blanket grant (`ConsentGrant.service is None`) given three
weeks ago for a **garbage** complaint does **not** cover a **water** case.
Re-ask rather than assume.

Logic:
- filter `grants` with `g.is_live(now)` — this is why `now` is passed in, and
  why it must be **naive** (trap T1)
- require `g.scope == scope`
- if `g.service is None` → blanket → **drift check fails**, return
  `(False, "<readable reason>")`
- if `g.service != service` → `(False, reason)`
- exact match on live + scope + service → `(True, grant_id)`

The second element is a **human-readable string** — Ali's trace UI renders it.

In production the grants come from `core.db.live_consents(household_id, now)`,
but this function takes the list directly, so tests need no store. Build grants
with `fakes.a_consent(...)` — it defaults to a live `FILE_INDIVIDUAL` grant for
`Service.WATER` at `T0`. Override `service=None` for the blanket-drift case and
`service=Service.GARBAGE` for the wrong-service case.

> **The argument to remember, it goes in the video:** a component that both
> holds the secrets and decides disclosure cannot audit itself. That is
> separation of duties — it is *why* the Warden is its own agent and not a
> prompt instruction inside the Household Agent.

### Block 4 — `agents/watchdog.py` (all three functions)

This is the demo's peak and it is fully deterministic, so it belongs on Day 1,
not squeezed into Day 2. It needs no model.

**First, fix the stale `Tier 3` in the `climb()` docstring → Tier 4 (D1).**

Add a trace helper emitting **exactly** Ali's format, tagged with `case_id`:
```
DISPUTED    watchdog    -> 7 live claims contradict closure
TRACKING    watchdog    -> SLA 7d, wake scheduled
PAUSED      watchdog    -> endpoint unreachable, clock held
ESCALATED   watchdog    -> Assistant Executive Engineer
```

**`watchdog(case_id, action) -> None`** — one entry point, both clocks.
Dispatch on the T5 vocabulary: `check_sla`, `check_closure`, `expire_draft`.
Stateless between wakes: load the case from `core.db.get_case()` every time, hold
nothing in module state. **No `if demo_mode:` — ever.** If you feel you need it,
the clock is wrong; fix the clock.

> AgentCore Runtime's 8-hour session is a **session ceiling, not a scheduler**.
> Statutory windows are days. That is why this is stateless and why all case
> state lives in Kartik's DynamoDB.

**`reconcile_closure(case_id) -> bool`** — the moment the project exists for.
The institution says *resolved — supply restored*. Live claims from other
households say otherwise. Return `True` to dispute.

- `case = db.get_case(case_id)`
- `closed_at = clock.now()` — the moment of this `check_closure` wake (trap T9;
  there is no `closed_at` on the frozen `Case`)
- `claims = db.claims_in_window(case.segment, case.service, since=closed_at)`
- apply the T6 liveness rule, then count **distinct households**:
  `len({c.household_id for c in claims})`. Two member agents in one household is
  **one** household, and `the_outage()` ships a deliberate duplicate
  `household_id` to catch exactly this mistake
- dispute when the count ≥ 1; emit `DISPUTED  watchdog  -> N live claims
  contradict closure`

This is the single thing in the system a person genuinely could not do for
themselves — **you know your own tap, not your neighbours'.** Give it a clean
log line; Ali is putting it on screen.

**`climb(case_id, clock) -> int`** — advance one tier, return the new tier.

- get the ladder via `agents.remedy.lookup(service, segment, feeder_id)`
  → `JurisdictionEntry.ladder` → `list[EscalationStep]`
- **never hardcode tier numbers or day counts** — read `tier`, `authority`,
  `window_days`, `statute_ref` from the ladder
- build a `Filing`, call `filing.compute_key()`, submit via
  `core.db.put_filing_once()`. On `(False, stored)` **do not file again** — a
  retrying Watchdog that files twice produces a duplicate that reads as spam
  and gets both copies closed (hard rule 5)
- schedule the next wake: `clock.schedule(case_id, deadline, "check_sla")`
- **Tier 4 = RTI: draft only.** It needs a citizen name, address and ₹10 fee and
  the system supplies **none of the three**. This is a guardrail, not a
  limitation to apologise for. Assert it in a test.

Three behaviours the failure-mode table promises — implement all three:
- institution unreachable → **pause the SLA clock** (`case.sla_paused = True`),
  retry twice, then surface. Never run a clock against a filing that never
  landed.
- draft unsigned after 7 days → expire it, one notice, `CaseStatus.DORMANT`
- household withdraws → honoured **retroactively**: corroboration count drops
  and the filing is amended

**`tests/test_watchdog.py`** — no monkeypatching (D2). Use the real
`core.db` on its default memory backend, seed it with `fakes`, and take the
`clock` and `outage` fixtures from `tests/conftest.py`.

`outage` gives you twelve claims on feeder `bwssb-tm-14` plus a decoy on
`bwssb-tm-22`, and a `case` — which is precisely the false-closure scenario:
close the case, leave the claims live, assert the dispute. Note two of the
twelve deliberately **share a `household_id`** (two member agents in one
household is **one** household), so if you ever count households, count
`len(set(...))`, not `len(...)`.

The ladder is already curated in `data/jurisdiction/ward12.sample.yaml` and I
verified it matches the ruling — tier 1 Section Officer 7d, tier 2 AEE 7d,
tier 3 grievance portal 15d, **tier 4 RTI (drafted only) 30d**. Load it; do not
retype it into a fixture.

Required tests: a false closure with live claims returns `True`; a genuine
closure with no live claims returns `False`; `put_filing_once` returning
`(False, stored)` files exactly once; unreachable pauses the clock; tier 4
produces a draft containing no name, address or fee.

**End of Day 1 gate:** `pytest` green with **no AWS credentials in the
environment**. Prove it by unsetting `AWS_PROFILE` for one run.

---

# DAY 2 — The household, integration, hardening

Day 2 is the model-dependent half plus everything that touches other lanes.

### Block 5 — `agents/intake.py`

Text in. **Voice is out of scope — do not start a Twilio trial.**

`parse(raw_text, member) -> list[dict]`
**One sentence often contains more than one problem.**
*"Three days now, no water in the tank, and I have to send Divya to school
tomorrow"* is a supply failure **and** a transport need → **two dicts**.
Returning one is the bug this function exists to prevent.

`read_back(needs, language) -> str`
Confirmation in the member's own language (`MemberContext.language`:
`en | kn | hi | ta`). **Bad transcription pursued for eleven weeks is failure
mode #1.** Cheap to build, shows well on camera.

Per D3: add an injectable `model=None` parameter defaulting to
`os.environ["MODEL_SMALL"]`. Tests inject a fake returning canned JSON.

**`tests/test_intake.py`:** the two-need sentence yields exactly 2 dicts;
`read_back` echoes every parsed need. Fake model, no credentials.

### Block 6 — `agents/household.py`

`build_swarm(members)` — apply trap **T4** first, then:
```python
Swarm([parent, teen, elder], entry_point=parent, max_handoffs=6,
      execution_timeout=90.0, node_timeout=30.0)   # + max_iterations=8 ONLY if in the signature
```

`deliberate(members, need) -> HouseholdPosition`

**Only run the swarm when a need touches more than one member.** A wrong
electricity bill needs no family debate, and burning a swarm on it is waste —
short-circuit to a single-member position.

**The thing that makes this layer justify itself:** the returned position can
carry facts the reporter never mentioned. The fixture already exists —
**`fakes.the_family()`** returns Lakshmi (parent, works 09:00-18:00), Divya
(teen, chemistry exam 09:00) and **Shanta (elder, "dialysis Tue and Fri",
"needs 40L before 06:00")**. The parent reports only "no water"; the position
must come back carrying the 06:00 deadline pulled from the grandmother's
context. That is one of the three best moments in the demo — and the same
sensitive fact the Warden must then refuse to leak in Block 2.

**Return `HouseholdPosition`. Never a `Claim`.** Only the Warden makes those.

> `Swarm` maintains a **mutable `SharedContext` every agent reads and writes.**
> That is correct inside one household and catastrophic across households — it
> is the verified reason the mesh uses A2A rather than a bigger swarm. Know that
> sentence; it goes in the video.

**`tests/test_household.py`:** the dialysis fixture asserts
`position.hard_deadline` is set and `deadline_reason` is populated **from a
member the reporter never mentioned**; a single-member need does not invoke the
swarm; the return type is never `Claim`.

### Block 7 — `agents/warden.py` → `check_inference_leak()`

**Do this only once Blocks 2 and 3 are green.** It is the designated cut if
Friday goes wrong — but it is also the most original thing in the project, so
cut it before you cut anything of Kartik's, never before.

`check_inference_leak(claim, history) -> tuple[bool, str]`

A household that declines Tuesday **and** Friday swaps has told the mesh that
someone has a Tuesday-Friday commitment. **The leak is in the correlation, not
in any single field**, so no schema catches it. Compare the new claim against
`history` for a pattern that reconstructs a withheld fact; return
`(True, readable_reason)` when it does.

The fixture is already waiting for you: `fakes.the_family()`'s elder carries
`unavailable=["tuesday", "friday"]` — the exact commitment this check must stop
the mesh from reconstructing. Note the round trip that makes the demo land:
Block 2 strips `deadline_reason="dialysis prep"` from the claim, and this block
stops the mesh from inferring it back out of the Tuesday-Friday pattern.

**`tests/test_warden.py`:** the Tuesday+Friday sequence trips it; an unrelated
sequence does not.

### Block 8 — Integration surface for Ali

Ali's `graph/request_path.py` does `builder.add_node(intake_agent, "intake")`
and `add_node(warden_agent, "warden")` — it needs **agent objects**, but your
stubs expose plain functions. `household_swarm` is fine: a `Swarm` is a valid
node and `build_swarm()` already returns one.

Add thin factory functions **in your own files** — additive, nothing existing
changes:
- `agents/intake.py` → `build_intake_agent(model=None)`
- `agents/warden.py` → `build_warden_agent(model=None)`

**Post these five things to the group — every one is merge-blocking if it
surfaces on Thursday instead:**

| # | Tell | Who needs it |
|---|---|---|
| 1 | the two factory names above | Ali — his `GraphBuilder` nodes |
| 2 | the T5 action vocabulary `check_sla` / `check_closure` / `expire_draft` | Ali — his Watchdog Lambda dispatches on it |
| 3 | **T8: who owns `escalation_tier` writes** | Kartik — needs a decision, then the STATUS.md decisions log |
| 4 | T10: any optional `core.db` function you relied on is now required in `store.py` | Kartik |
| 5 | T3: `pyproject.toml` `pythonpath = ["."]` so bare `pytest` works | Ali — shared plumbing |

Also **surfacing is not yours.** Your failure-mode branches say *"retry twice,
then surface"* — surfacing means handing the decision to Ali's
`agents/digest.py`, which picks **one** recipient in their own language. Emit
the trace line and stop; do not build a notifier.

### Block 9 — Final sweep

1. **The utcnow grep** (D4 — `core/types.py` and `core/clock.py` are exempt):
   ```bash
   grep -rn "utcnow" --include="*.py" . | grep -v "core/clock.py" | grep -v "core/types.py"
   ```
   Must return nothing. **Check other people's files too** — your brief makes
   this your job repo-wide. If you find one in another lane, message the owner;
   do not edit their file.
2. `grep -rn "demo_mode" agents/watchdog.py` → must return nothing.
3. `ruff check .` → clean.
4. `python -m pytest -q` → **green**, with AWS credentials unset (trap T3: run
   it from the repo root, and never as bare `pytest`).
5. `PANCHAYAT_BACKEND=dynamodb python -m pytest -q` → run it once Kartik's
   `store.py` is real. Same tests, both backends. If memory passes and DynamoDB
   fails, **the DynamoDB one is wrong** — and you found it on your own bench
   instead of during Thursday's integration.
6. **Update your row in `STATUS.md`.** Your teammates' Claude sessions cannot
   see this one; that file is the only way their agents learn that
   `clock.py`, `warden.py` and `watchdog.py` are real and what shape they took.
   Ten seconds, and it stops someone rebuilding what you just finished.

---

## Definition of done

- [ ] `test_clock.py` proves 7 virtual days fire in ~7 real seconds
- [ ] `Clock.now()` returns naive UTC everywhere (trap T1)
- [ ] Zero `utcnow` outside `core/clock.py` and `core/types.py`
- [ ] No `if demo_mode:` anywhere in `agents/watchdog.py`
- [ ] A fixture where the household position carries a fact the reporter never said
- [ ] `minimise()` provably drops budget and health fields — tested adversarially
- [ ] `reconcile_closure` disputes a false closure using other households' claims
- [ ] Tier 4 RTI is draft-only, with no name, address or fee
- [ ] `put_filing_once` returning `(False, stored)` never files twice
- [ ] Whole suite runs with **no AWS credentials** (`python -m pytest`, memory backend)
- [ ] `test_virtual_clock_compresses_a_statutory_week` is green again (trap T7)
- [ ] Nothing in your files imports `core.store` or `core.memstore` directly — only `core.db`
- [ ] `escalation_tier` ownership (T8) raised in the group and written to the STATUS.md decisions log
- [ ] Every commit is on **`feat/household-time`**; `main` untouched, no `--no-verify`
- [ ] Your rows in `STATUS.md` are current
- [ ] `ruff check .` clean

## Your Day 1 gate

STATUS.md already names it, and it is the one thing to report at the evening
sync — **the result, not the vibe:**

> **Raghav — `test_clock.py` proves 7 virtual days fire in ~7 real seconds.**

Fill in the `Result` cell in the *Day 1 gates* table when it passes. If it does
not pass, say so that evening. A gate that quietly slips to Thursday is the
expensive kind.

## Cut order if you run out of time

Per Ali: escalation tiers 3 and 4 → `check_inference_leak()` → polish.
**Never cut `minimise()` or `reconcile_closure()`** — they are the lane.
