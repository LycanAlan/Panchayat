# Review — `feat/household-time`

Reviewed by Ali, 11 Sep, against branch tip `c990c7e`. Run manually (the
`/code-review` skill hit its session limit mid-pass) — same standard: every
finding below was reproduced by executing your code, not inferred from reading
it. Each has a paste-able repro.

56 passed / 1 honest skip on your lane, `ruff` clean on every file you touched.
This branch is careful work — the injected-dependency structure in all four
modules, the `LeakDetector` subclass point, checking `Swarm`'s constructor via
`inspect` instead of guessing — all of that is the right instinct and it shows.

---

## Verdict

**One blocker.** It's the most consequential finding across all three branches
today, and it's in the function the whole demo's peak moment depends on.

---

# Blocker

## B1 — `reconcile_closure` checks the wrong direction

Your own docstring says it well: *"THE moment the project exists for... Returns
True to dispute — using ground truth a citizen could never have."* The code:

```python
closed_at = clock.now()
claims = self.db.claims_in_window(case.segment, case.service, since=closed_at)
```

`claims_in_window(..., since=X)` returns claims with `created_at >= X`. Using
`clock.now()` as `since` means it only counts claims **created at or after the
exact instant the check runs** — claims from the future relative to the query.
Verified two ways:

```python
# Seven households already filed on this segment/service BEFORE the check --
# the realistic case, and the exact scenario the trace line names:
#   "DISPUTED  watchdog  -> 7 live claims contradict closure"
for i in range(7):
    db.put_claim(fakes.a_claim(segment=case.segment, service=case.service,
                                created_at=now - timedelta(hours=i+1)))
wd.reconcile_closure(case.case_id, clock=clock)
# -> CLOSED, "no live claims -- closure stands"      (should be DISPUTED, 7)

# A claim dated in the FUTURE relative to the check:
db.put_claim(fakes.a_claim(..., created_at=now + timedelta(hours=1)))
wd.reconcile_closure(case.case_id, clock=clock)
# -> DISPUTED, "1 live claim(s)"
```

Backwards. A closure check that only detects claims that haven't happened yet
will never fire on real evidence, and will always be able to fire on nothing
(since no claim is ever actually dated in the future). Run against production
data, this always returns `CLOSED — closure stands`, silently, for every case.

**Why your own tests pass:** `test_reconcile_closure_disputes_using_other_
households_claims` uses `RecordingClock(now=fakes.T0)` and claims dated
`>= fakes.T0`, so the check instant and the claims' floor are pinned to the
same value — the `>=` boundary happens to include them. That coincidence never
occurs in production: a check always runs *after* the claims it's meant to
catch were filed, never at the identical instant.

`Case` genuinely has no `closed_at` — your docstring is right that the frozen
contract doesn't give you one — but "now" is the wrong stand-in for it. The
direction that matches the docstring's own claim ("new reports arriving after
the institution announced resolved") is a **look-back window**, not a
look-forward one: claims that already exist and are recent relative to the
check, not claims from later than the check. Something anchored to
`case.sla_deadline`, `case.created_at`, or a bounded recent window (last N
days) before `now` — not `now` itself as the floor.

Not asking you to pick the exact anchor here — that's a real design call
(how far back is "still evidence this wasn't resolved"?) and it's yours. But
the fix has to look backward from the check instant, not forward.

---

# Everything else — small, and none of it blocks

## The timer-resolution flake, same root cause as one I fixed on main today

```
tests/test_clock.py::test_now_advances_monotonically
assert b > a   # both timestamps identical
```

```python
# measured directly:
resolution: 0.015625            # Windows' monotonic() tick, 15.6ms
same-tick occurrences: 67/200   # under a 10ms sleep
```

Same class of bug as `test_virtual_clock_compresses_a_statutory_week`, which I
fixed on main this morning (`0befb9b`) after Alakshendra hit it 5/5 — Windows'
`time.monotonic()` has coarse resolution, so two calls close together can land
in the identical tick and a strict `>` (or `.days ==`) assertion becomes a coin
flip. You forked before that fix landed and hit the same platform trap
independently in a new test file, which is exactly bad luck rather than
anything wrong with your reasoning. The fix there was the same shape it'll need
here: don't assert strict inequality on two nearby wall-clock reads: sleep long
enough that the resolution can't hide the delta, or assert on a **derived**
property (the virtual elapsed time crossed some expected threshold) instead of
comparing two `now()` values directly.

## An integration seam — mine, not yours, flagging so it doesn't surprise you

Your `minimise()` docstring is explicit and correct: *"HouseholdPosition
carries no segment/feeder_id/service — the graph populates those on the
returned Claim... Not this lane's job."* Checked what that actually produces
right now:

```python
minimise(fakes.a_household_position())
# -> segment='' feeder_id='' service=Service.WATER (default) consent_scopes=[]
```

My `graph/request_path.py`'s `_warden` node currently does `ctx.claim = claim`
and passes it straight to `remedy.resolve()` with no field population in
between. Once your real `minimise()` merges, every claim routes with an empty
segment and the wrong default service, and `resolve()` returns `UNROUTED` for
everything regardless of what was actually reported. **This is my fix, in my
file** — `_warden` needs to backfill `segment`/`feeder_id`/`service` from the
request payload onto the claim after `minimise()` returns, same as the fallback
stub already does. Landing it before I merge your branch. Flagging only so you
know the boundary held on your side and the gap is on mine.

One thing worth confirming while I'm there: `consent_scopes` comes back empty
too, same as the platform-lane fallback — so the `UNCONSENTED` trace note I
added in the spine review applies to the real Warden output as much as the
stub. Not new, just noting it stays true once merged.

## `climb()` — worth a second look, not a finding

Retrying the submit exactly twice (`self._submit(filing) or self._submit(filing)`)
before pausing: reasonable, but worth deciding out loud whether "twice,
synchronously, no backoff" is the intended retry policy for the real A2A
handoff once Alakshendra's `institutions/client.py` is what `submit` actually
calls, or just a placeholder shape. Not blocking — the pause/resume path
around it is correct and tested.

## Two of your open items, answered

**Your item 6** (the flaky clock test) — see above, same bug, independently
found; your diagnosis of the mechanism was exactly right.

**Your item on `core/types.py`'s `utcnow()`** — already fixed on main
(`8f14986`), moot as you guessed. Your `_utcnow()` naive-UTC helper in
`core/clock.py` and the `get_running_loop()` fix are both real improvements
independent of that and worth keeping through the rebase — the `get_running_loop()`
catch in particular is one I didn't have: `call_later` only ever fires while a
loop is running, so `get_event_loop()`'s old behavior could silently never fire
a scheduled wake outside one. Good catch.

**Your unresolved T8** (the `escalation_tier` dual-writer race with Kartik's
`apply_upgrade()`) — right to flag rather than resolve unilaterally. Same shape
as a stale-write hazard Kartik's review turned up independently in
`core/store.py`'s `put_case`. Bringing both to the group together once his
branch is in — they're likely the same fix (a version guard on `Case` writes).

---

# Suggested order

1. **B1** — this is the one. It's small in code, large in consequence: the
   dispute the whole video's peak moment rests on currently cannot fire.
2. The timer flake in `test_clock.py` — five minutes, same pattern as the
   fix already on main.
3. Rebase onto current `main` when B1's in — your branch is 13 commits behind
   and conflicts on `STATUS.md` and `core/clock.py`, both of which are just
   both-sides-touched-it, not real disagreements.

Everything else above is FYI, not a to-do. Ping when B1's fixed and I'll
re-review and merge.
