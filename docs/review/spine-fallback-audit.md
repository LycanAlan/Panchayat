# Spine fallback audit + `feat/household-time` merge status

By Raghav, 11 Sep, updated same day after Ali's reply. Three parts: where my
branch actually stands after Kartik's merge-readiness pass, the audit he
named but left open, and confirmation of what Ali fixed in response — each
re-verified independently rather than taken on his word, same as everything
else in this doc.

> *"Every fallback in `request_path.py` deserves the same audit."*

Method is the one Ali and Kartik have both used on this repo: every finding
below was reproduced by executing the code, not inferred from reading it.
Each has a paste-able repro. Run everything from the repo root with
`python -m pytest`, never bare `pytest`.

---

## Part 1 — my branch, and an apology for wasted review time

**Two of Kartik's three blockers were already fixed when he reviewed them.**
He was reading `origin/feat/household-time`, which was **13 commits behind my
local work** — the rebase and the B1 fix were sitting unpushed on my machine.
That is my fault, not his, and it cost him a review pass. The branch is now
pushed and current.

| Blocker | Status |
|---|---|
| `core/clock.py` conflict | **Resolved.** Rebased onto `main`; branch is 0 behind. I kept main's `_ACTIVE` / `reset_clock()` memoisation wholesale — the exact "silently reintroduce multiple timelines" trap Kartik flagged. My `get_running_loop()` fix survived the rebase; `main` still doesn't have it. |
| `reconcile_closure` looks forward (Ali's B1) | **Fixed.** Now `since = clock.now() - timedelta(days=self.closure_lookback_days)`. The version he tested had `closed_at = clock.now()`. |
| Spine breaks, 5 tests | **Not mine, and structurally cannot be.** See below. |

Verify:

```bash
git fetch origin
git rev-list --count origin/feat/household-time..origin/main   # 0
git show origin/feat/household-time:agents/watchdog.py | grep "since = clock.now()"
```

**On the 5 spine failures.** Reproduced them (installed `strands` to do it
properly rather than take it on faith): 5 failed, 3 passed, single root cause
— `segment=''`, `feeder_id=''` on the emitted Claim.

It cannot be fixed in `minimise()`. `HouseholdPosition` is frozen and carries
no `segment`, `feeder_id` or `service`, so there is nothing for the function
to emit. `graph/request_path.py::_warden` does `ctx.claim = claim` with no
backfill, while `_minimise_fallback` — the stub it replaced — pulls all three
from `ctx.payload`. Ali found this and claimed the fix; Kartik confirmed it
independently by patching the fields back on (→ 8 passed). Recording it here
only so the sequencing is unambiguous: **my branch does not break the spine on
its own, but merging it before Ali's backfill lands leaves 5 red.**

My lane: **62/62 green.** One bonus from installing `strands` — it un-skipped
`test_build_swarm_requires_strands_installed`, which now genuinely runs and
passes. So `Agent(name=...)` and the `inspect.signature` guard for
`max_iterations` (which I had flagged as unverified and possibly wrong) are
**correct against real strands 1.55.0**. That caveat can come out of the
docstring.

---

## Part 2 — the fallback audit

Kartik's framing is the right one and generalises: *the stub was more capable
than the real implementation it stood in for, which is backwards from what
stubs are for.* Three of the four findings below are that same shape.

### F1 — `_minimise_fallback` contradicts its own docstring

`graph/request_path.py`. Owner: Ali. **Latent, not live. Fixed on his
current branch** — the fallback (now `_claim_stub`) no longer copies
`position.summary` through, and the docstring argues it from hard rule 2
directly rather than from a promise the code didn't keep.

```python
def _minimise_fallback(ctx: RequestContext) -> Claim:
    """Deliberately conservative: reduce, never copy through. A stub that
    leaked would make the membrane look like it works when it does not."""
    ...
    description=pos.summary,
```

It copies through. `pos.summary` is household-authored free text from inside
the membrane, and it lands verbatim in `Claim.description`, which crosses it.

The real `warden.minimise()` builds `description` **only** from
`position.needs` and never reads `summary`, `raw_report` or
`contributing_members` at all — that is a structural guarantee rather than a
scrub, which is why it survives an adversarial test with names and figures
planted in those fields. So the stub is **less** privacy-safe than the real
implementation while its docstring claims the opposite.

Latent because the fallback only fires on `NotImplementedError`, which stopped
happening once the real Warden landed. Worth fixing anyway: it is the
documented behaviour of the fallback, and the next person to stub the Warden
inherits a leak with a docstring telling them it cannot happen.

### F2 — intake stub and real `parse()` emit disjoint key sets

Half mine. **The frozen stub only specified `-> list[dict]`, so no key schema
was ever agreed** — Ali picked one, I picked another, and neither is wrong
alone.

```
_intake stub emits:   {"service", "summary"}
intake.parse() emits: {"description", "member_id", "raw_text"}
household.deliberate() reads: need.get("description"), .get("household_id"), .get("raw_text")
```

Under the stub, `deliberate()` receives `description=""` and the reported text
is silently discarded. Two adjacent stubs hid this from each other — the
household node was stubbed too and returned `fakes.a_household_position()`
regardless of its input, so nothing downstream ever noticed the empty string.
Same class as the `segment=''` bug, one layer up the graph.

Live path (real intake → real deliberate) is fine. The stub path drops text.
The real shape is the richer one, so the stub should conform to it, not the
reverse — one line. Flagging rather than editing `request_path.py` myself.

**Fixed on Ali's current branch** — the stub now emits `"description"`
directly, and the trace-rendering code checks `("description", "summary",
"raw_text")` in order rather than assuming one key.

### F3 — ternary precedence bug in `_household`'s trace line

`graph/request_path.py`. Owner: Ali. **Live at the time this was found, fixed
on his current branch** — restructured out of the ternary entirely.

```python
str(len(position.contributing_members)) + " members reconciled, "
"hard deadline " + position.hard_deadline.strftime("%H:%M")
if position.hard_deadline else "no hard deadline"
```

`A + B + C if cond else D` binds the conditional to the **whole**
concatenation, not the last term. Reproduced by executing the exact
expression:

```
hard_deadline=None  -> 'no hard deadline'
hard_deadline=06:00 -> '2 members reconciled, hard deadline 06:00'
```

So whenever there is no hard deadline, the line silently loses the member
count. Small, but the trace *is* the product surface — this is a visible
regression on precisely the artifact being demoed. Needs parens around the
conditional term.

### F4 — `AWS_PROFILE=""` produces a fake failure that looks like a code bug

Environment, affects everyone. Setting the variable to empty — the natural way
to "unset" it when proving the suite needs no credentials — makes botocore
reject it as a profile literally named `''`, from inside strands' `Agent`
construction:

```
botocore.exceptions.ProfileNotFound: The config profile () could not be found
```

It surfaces as a failure in `tests/test_household.py` and reads like a defect
in `build_swarm()`. It is not. Use `env -u AWS_PROFILE` instead of
`AWS_PROFILE=`:

```bash
env -u AWS_PROFILE -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY python -m pytest -q
```

Worth a line in CLAUDE.md next to the offline-suite claim, before it costs
someone an hour.

---

---

## Part 3 — confirmed fixed, independently re-verified

Ali replied same day with fixes for both blockers from Part 1's cumulative
merge test, on a new branch (`feat/plat-day2-groundwork` — the one this was
tested against, `feat/plat-spine-review-fixes`, has since been deleted,
presumably superseded). Checked each in an isolated `git worktree` rather than
touching this branch's tree, and confirmed both hold:

**B2, `segment=''`** — `_warden` now calls `_apply_request_context(ctx, claim)`
on both the real and the stub path, so the backfill can't be skipped by
whichever branch fires. `tests/test_request_path.py`: **19/19 passed** in a
clean worktree checkout of his branch.

**B1, the shared jurisdiction table** — his test now does
`entry = copy.deepcopy(shared)` before mutating `entry.ladder = []`, with a
comment crediting the find and correctly pointing the real defect (a
module-level cache in `agents/remedy.py` handing out mutable references) at
Alakshendra rather than working around it locally. Verified in-process, not
just by reading the diff — ran his full test file, then queried
`remedy.lookup()` in the **same Python process** immediately after:

```
SAME PROCESS, after the full file ran: ladder has 4 tiers
```

Table survives. Both blockers are closed on his branch.

**A third finding from his reply, worth recording:** a filing built with
`authority=entry.authority` (the table's top-level string, e.g. `"BWSSB"`)
rather than the tier-specific `step.authority` (e.g. `"BWSSB Assistant
Engineer, sub-division office"` for tier 1) breaks hard rule 5 across two
writers — `Filing.compute_key()` hashes the authority string, so the graph's
initial filing and the Watchdog's later `climb()` call would compute
**different keys for the same filing**, and `put_filing_once()` would never
see the collision it exists to catch. Checked my own `climb()` against this:
it already uses `step.authority`, correctly —
`agents/watchdog.py:215`. My idempotency test
(`test_climb_does_not_file_twice_on_a_retry`) derives the authority live from
the real ladder specifically so it can't drift back into this mistake
silently. Recording the shape of the bug here since it's the kind of thing
that reappears wherever a `Filing` gets constructed.

**Not done, and deliberately not done now:** Alakshendra's
`compose_filing()` (curated `required_fields`, refuses on missing data,
tested against the real desk) should replace my `Watchdog._draft_filing()` /
`_draft_rti()`, which do the same job with fixed string interpolation and no
missing-field check. Both Ali and Alakshendra agree it's mine to delete. Not
doing it in this pass: `compose_filing()` lives only on
`alakshendra/ladder-and-filing-client`, unmerged, and importing from it now
would make this branch depend on one that isn't in `main` yet — exactly the
kind of premature coupling the fake-based "nobody waits for anybody" setup
exists to avoid. Once his branch merges, this is a straightforward deletion:
swap the two private methods for a call to `remedy.compose_filing()`, keep
the `is_rti` branch's draft-only behaviour, done.

---

## Repo state at time of writing (original audit, `feat/household-time` alone)

```
105 passed, 5 failed, 1 skipped, 2 errors
```

- 5 failed — all `tests/test_request_path.py`, all the `segment=''` root
  cause (F2/B2 above). **Fixed on `feat/plat-day2-groundwork`, 19/19 passing,
  independently re-verified in an isolated worktree — see Part 3.**
- 2 errors — `test_institutions.py` / `test_remedy.py`, a Windows temp-dir
  permission issue in pytest's `tmp_path`, environmental rather than code.
- 1 skipped — unrelated.

## Status of every finding as of Part 3

| # | Finding | Owner | Status |
|---|---|---|---|
| B1 | Shared jurisdiction table mutated by a test | Ali (his test) / Alakshendra (the underlying cache) | **Test fixed** (`copy.deepcopy`), verified in-process. Underlying shared-cache defect still open, correctly left to Alakshendra. |
| B2 | `segment=''`, 8 spine tests red | Ali | **Fixed**, 19/19 re-verified independently. |
| F1 | Fallback copied `position.summary` through | Ali | **Fixed.** |
| F2 | Intake stub/real key mismatch | Ali (half mine — no schema was ever agreed) | **Fixed.** |
| F3 | Ternary precedence dropped member count | Ali | **Fixed.** |
| F4 | `AWS_PROFILE=""` fabricates a failure | environmental | Still worth a CLAUDE.md line; nobody's job specifically. |
| — | `Filing(authority=entry.authority)` vs tier-specific `step.authority` | whoever else constructs a `Filing` | Confirmed my own `climb()` already does this correctly; recorded as a general hazard, not a bug in my lane. |

**Everything Ali could fix on his side of the boundary is fixed and
independently re-verified**, not merely re-read from his message.

## Deliberately not touched

- **`escalation_tier` / `put_case` race** — Kartik has taken the remaining
  half (`climb()`'s read-write window dropping a household that joins between
  read and write). His measurement on DynamoDB Local, his file.
- **`_REF_RE` on `REOPENED`** — Kartik already found and fixed it.
- **`signed_by` for tiers 1-3, and the `submit`/`DeskReply` shape** — still a
  group decision, documented in `agents/watchdog.py` and STATUS.md. Not a
  policy choice between "sign once" and "sign per tier": there is no signature
  capture step anywhere yet, for any tier.
- **`_draft_filing()` / `_draft_rti()` → `compose_filing()`** — mine to
  delete, blocked on Alakshendra's branch merging first. See Part 3.
- **The module-level cache in `agents/remedy.py`** — Alakshendra's file;
  flagged by both Ali's fix comment and this doc, not fixed here.
