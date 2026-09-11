# Merge readiness — `feat/household-time` (Raghav)

Reviewed by Kartik, 11 Sep, against `c990c7e` merged into `upstream/main`
(`0d899e9`). Every finding below was **reproduced by executing it** in a
throwaway worktree, not inferred from reading the diff. Paste-able
reproductions are inline.

This is a *merge-readiness* review and does not replace Ali's
`docs/review/household-time.md`. Where a finding is his, it says so.

---

## Verdict

**Not mergeable as it stands.** Three things block it, and only one of them is
a defect in Raghav's own code.

| # | Blocker | Owner | Status |
|---|---|---|---|
| **M1** | `core/clock.py` conflicts; resolving it wrong silently reverts a main fix | Raghav (rebase) | open |
| **M2** | Merging breaks the request spine — 5 tests fail | **Ali** | open, Ali has claimed it |
| **M3** | `reconcile_closure` looks forward instead of backward | Raghav | open |

The good news is that M2 is already diagnosed and owned by Ali, and M1 is
mechanical. **M3 is the only one that needs Raghav to design something.**

### Numbers

```
branch as-is                    56 passed, 1 FAILED
branch merged into main         103 passed, 5 FAILED, 1 skipped
ruff check (his lane)           clean
behind main                     13 commits
```

---

## What is right, and should be said first

**The privacy membrane is the strongest thing on any branch today.** Hard rules
2 and 9 hold structurally, not by scrubbing. `minimise()` builds `description`
only from `position.needs` and never reads `summary`, `raw_report` or
`contributing_members`, so sensitive content cannot leak through it *by
construction*. Tested adversarially with everything loaded into the fields the
Warden is supposed to ignore:

```python
pos = a_household_position(
    summary="Shanta needs 40L before 06:00 for dialysis at Manipal",
    deadline_reason="dialysis prep -- kidney failure",
    budget_ceiling_inr=500,
    raw_report="We earn 12000/month, 3 months rent arrears, Divya missing school",
    contributing_members=["Lakshmi (parent)", "Shanta (elder, dialysis)"])

warden.minimise(pos)
# description = 'water supply restored'
# dialysis / kidney / 12000 / arrears / school / Shanta / Lakshmi / Divya
# / Manipal / 500  -- ALL ABSENT
# priority=high  reason_withheld=True  has_budget_ceiling=True
```

Ten sensitive tokens, zero leaks, and the reduced markers all set correctly.
That is the hardest requirement in the project and it is met.

**Hard rule 1 is clean.** No `utcnow()` or `datetime.now()` anywhere in
`agents/warden.py`, `watchdog.py`, `intake.py` or `household.py`. All time
arrives through `Clock`.

**`_utcnow()` is better than what main has.** Main fixed the same deprecation by
inlining `datetime.now(timezone.utc).replace(tzinfo=None)` in two places.
Raghav's named helper with a docstring explaining *why* naive-UTC is required
(`ConsentGrant.is_live()` compares against naive defaults) is the better
version, and the merge below keeps it.

**`climb()` names the race it cannot fix alone** rather than guessing — see M4.
That is the right instinct and it turned out to be correct; see below.

---

# M1 — `core/clock.py` conflicts, and the obvious resolution is wrong

```bash
git merge-tree --write-tree --name-only upstream/main upstream/feat/household-time
# CONFLICT (content): Merge conflict in STATUS.md
# CONFLICT (content): Merge conflict in core/clock.py
```

`STATUS.md` is the shared brain and conflicts on every branch; it is noise.
`core/clock.py` is not noise.

**Why it conflicts.** The branch point is `fa7ff91`, which did not have
`get_clock()` memoisation. Main added it in `8f14986`. Raghav then edited the
same region for the naive-UTC fix without that commit. So his side of the
conflict is *the pre-memoisation version* — not a deliberate revert, but
textually indistinguishable from one.

**Why that is dangerous.** Taking "his" side of the third hunk drops this:

```python
_ACTIVE: Clock | None = None

def get_clock(...):
    # MEMOISED, and that is not an optimisation. A VirtualClock fixes its epoch
    # and its monotonic origin at construction, so two of them are two unrelated
    # timelines. Under TIME_SCALE=86400, a clock built ten real seconds after
    # the first reports a virtual `now` TEN DAYS earlier than its sibling.
```

It also drops `reset_clock()`, which main's tests use. A resolver working
quickly, seeing Raghav owns `core/clock.py`, and taking his side wholesale
reintroduces multiple timelines per process — and the Watchdog then fires at
nonsense times or never.

**The correct resolution**, which I ran and verified:

- hunks 1 and 2 → **take Raghav's** `_utcnow()` helper (better than main's
  duplicated inline expression)
- hunk 3 → **take main's** `_ACTIVE` memoisation and `reset_clock()`

**Cleanest fix: Raghav rebases on main first.** The branch is 13 commits
behind; almost all of this disappears on a rebase, and it also picks up the
clock-test fix (`0befb9b`) that currently fails on his branch.

---

# M2 — merging breaks the request spine. Ali's fix, but it must land first

```bash
git checkout -B x upstream/main && git merge upstream/feat/household-time
pytest tests/test_request_path.py
# 5 failed
```

Failing: `test_one_report_produces_one_filing`, `test_routing_is_grounded_and_
cited`, `test_nothing_is_submitted_without_a_human`, `test_refiling_the_same_
case_is_suppressed`, `test_the_claim_reaches_storage`.

The trace tells the story:

```
SIGNAL       intake     -> 1 need(s) from kn text
DELIBERATED  household  -> no hard deadline
MINIMISED    warden     -> claim emitted; withheld nothing
UNROUTED     remedy     -> no jurisdiction entry for  -- asking, not guessing
HELD         file       -> nothing to file against yet
```

`no jurisdiction entry for ` — with nothing after "for". The segment is empty.

```python
warden.minimise(fakes.a_household_position())
# segment='' feeder_id='' service=Service.WATER (default)
```

**One root cause explains all five.** Proved by patching only `segment` and
`service` back onto the Warden's output and re-running:

```python
_real = warden.minimise
def patched(position):
    c = _real(position)
    c.segment = "ward12-4thcross"; c.service = Service.WATER
    return c
warden.minimise = patched
# tests/test_request_path.py -> 8 passed
```

**This is not Raghav's defect.** `HouseholdPosition` is in the frozen
`core/types.py` and carries no `segment`, `feeder_id` or `service`:

```python
household_id, summary, needs, hard_deadline, deadline_reason,
budget_ceiling_inr, contributing_members, raw_report
```

`minimise(position)` cannot populate fields its input does not contain.
Raghav's docstring says exactly this and is correct.

**Ali has already found and claimed this** in `docs/review/household-time.md`:
*"This is my fix, in my file — `_warden` needs to backfill
segment/feeder_id/service from the request payload onto the claim after
minimise() returns, same as the fallback stub already does. Landing it before I
merge your branch."*

What I add is the measurement: it is **not** a soft integration note, it is
**five failing tests**, and the merge must not happen before Ali's backfill
lands. Sequencing matters here, so it belongs on the blocker list even though
the code to change is not Raghav's.

**The deeper lesson, worth a line in CLAUDE.md.** The stub was *more capable
than the real implementation*:

```python
try:
    claim = warden.minimise(ctx.position)   # real: no segment
except NotImplementedError:
    claim = _minimise_fallback(ctx)         # stub: segment from ctx.payload
```

Every fallback in `graph/request_path.py` should be audited for the same shape.
A stub that does more than the thing it stands in for makes the spine green
until the real module lands, which is precisely backwards from what stubs are
for.

---

# M3 — `reconcile_closure` looks forward, not backward

**Ali's B1.** Unfixed on `c990c7e` (his review postdates Raghav's last commit).
Reproduced independently:

```python
case = fakes.a_case(segment=SEGMENT, service=WATER, status=FILED)
# seven households that filed BEFORE the closure check -- the realistic case
for i in range(7):
    db.put_claim(fakes.a_claim(segment=case.segment, service=case.service,
                               household_id=f"hh_{i}",
                               created_at=now - timedelta(hours=i + 1)))
watchdog.reconcile_closure(case.case_id, clock=FixedClock(now))
# -> CLOSED  "no live claims -- closure stands"      dispute=False
```

```python
# one claim dated in the FUTURE, which cannot happen in production
db.put_claim(fakes.a_claim(..., created_at=now + timedelta(hours=1)))
watchdog.reconcile_closure(case.case_id, clock=FixedClock(now))
# -> DISPUTED  "1 live claim(s) contradict closure"  dispute=True
```

`claims_in_window(..., since=X)` returns `created_at >= X`, and the code passes
`since=clock.now()`. So it counts only claims from *after* the check instant,
never the evidence that already exists.

Run against real data this returns `CLOSED — closure stands` for every case,
silently, forever. It is the function the demo's peak moment depends on, and it
is the one thing in this lane that a judge will ask to see.

Ali is right that the anchor is a genuine design call and Raghav's. It has to
look **backward** from the check instant — `case.sla_deadline`,
`case.created_at`, or a bounded recent window — not forward.

**Why the existing test does not catch it:** `test_reconcile_closure_disputes_
using_other_households_claims` pins both the check instant and the claims'
floor to `fakes.T0`, so the `>=` boundary happens to include them. That
coincidence cannot occur in production, where the check always runs *after* the
claims it is meant to catch.

---

# M4 — not a blocker, and partly mine: `put_case` still clobbers membership

Raghav's `climb()` docstring flags this and declines to fix it unilaterally:

> *"Kartik's ambient `apply_upgrade()` also writes `case.escalation_tier` [...]
> and `db.put_case()` is a blind overwrite — two independent writers racing here
> is a real hazard (trap T8)."*

**He is right, and my Day 1 review fix only closed half of it.** I narrowed
`add_household_to_case` and `split_case` to conditional writes of the three
membership attributes, so ambient can no longer clobber the Watchdog's breach.
But `put_case` is still a whole-item write, and `climb()` calls it four times.
Measured on my branch against DynamoDB Local:

```python
watchdog_view = db.get_case(case_id)             # climb() reads
db.add_household_to_case(case_id, "hh_new", "clm_new")   # ambient lands
watchdog_view.escalation_tier = 2                        # climb computes
db.put_case(watchdog_view)                               # climb writes WHOLE item

db.get_case(case_id)
#   escalation_tier : 2    <- climb's write landed
#   household_ids   : []   <- the household that joined is GONE
#   merged_from     : []
```

A household that joins a case between the Watchdog's read and its write
disappears from it, and is then absent from the collective filing while
believing it joined. Aggregation is the product.

**Not blocking this merge** — `apply_upgrade()` does not exist yet, so nothing
races today. But it must be closed before Day 3, and the fix is in **my** file,
not Raghav's. I am taking it. Raghav was right to raise rather than patch.

---

# Suggested order

1. **Rebase on `main`.** Clears M1, picks up the clock fix, and removes 13
   commits of drift. Keep `_utcnow()`; keep main's `_ACTIVE` memoisation.
2. **Fix M3** — the look-back window. The only item needing a design decision.
3. **Wait for Ali's `_warden` backfill** before the merge lands (M2).
4. M4 is mine.

Once 1–3 are done and Ali's backfill is in, this branch should merge clean and
green. The lane itself is in good shape — the membrane work is the best privacy
implementation in the repo and none of the blockers touch it.
