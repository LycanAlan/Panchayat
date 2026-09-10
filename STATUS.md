# Status board

**Update your row when something lands. Takes ten seconds.**

This is not project-management theatre. Each of you has a separate Claude
session that cannot see the others. When Raghav's Claude reads this file it
learns that `store.py` is real and what shape it landed in, instead of guessing
or rebuilding it. That is the whole point.

Last updated: **10 Sep, 21:45** by Kartik

---

## Blockers right now

| Blocker | Who it stops | Workaround in place | Owner |
|---|---|---|---|
| **Bedrock not authorised** (AWS account flag, support case 178898467100367) | anything invoking a model | none needed yet, Day 1 work has no model calls | Ali |
| Collaborators not invited | Kartik, Alakshendra, Raghav cannot clone | — | Ali |

---

## Lane status

| Lane | Module | State | Notes |
|---|---|---|---|
| **shared** | `core/types.py` | **DONE, FROZEN** | Raise changes in the group |
| **shared** | `core/clock.py` | **DONE** | Real + virtual, one code path |
| **shared** | `core/memstore.py` | **DONE** | In-memory, full interface |
| **shared** | `core/db.py` | **DONE** | The seam. Import from here. |
| **shared** | `core/fakes.py` | **DONE** | `the_outage()` has 12 claims + a decoy |
| **shared** | `tests/` | **DONE** | 7 contract tests, no AWS needed |
| Kartik | `core/store.py` | **DONE** | DynamoDB, all 17 fns. On `feat/mesh-day1` (PR #1). Verified on DynamoDB Local, **not yet the real table**. |
| Kartik | `core/scoring.py` | **DONE** | `correlate()` renormalises when semantic is absent. `embed()` written but never executed. |
| Kartik | `agents/pattern_watch.py` | not started | |
| Kartik | `agents/anti_abuse.py` | not started | |
| Alakshendra | `data/jurisdiction/ward12.yaml` | not started | **sample with 4 entries exists** |
| Alakshendra | `agents/remedy.py` | not started | |
| Alakshendra | `institutions/` | not started | |
| Raghav | `agents/intake.py` | not started | |
| Raghav | `agents/household.py` | not started | |
| Raghav | `agents/warden.py` | not started | |
| Raghav | `agents/watchdog.py` | not started | |
| Ali | `graph/request_path.py` | not started | |
| Ali | `agents/digest.py` | not started | |
| Ali | AgentCore deploy | not started | **do this Day 2, not Day 4** |
| Ali | trace UI | not started | |

---

## Day 1 gates — report the result, not the vibe

| Who | Gate | Result |
|---|---|---|
| Alakshendra | 50 labelled complaints routed, **target ≥80%** | — |
| Kartik | `store.py` passes `tests/test_contract.py` on DynamoDB | **PASS, with a caveat.** 34/34 on both backends, twice in a row. Ran against **DynamoDB Local**, not our table -- no AWS credentials on this machine. Re-run needed when they land. |
| Raghav | `test_clock.py` proves 7 virtual days fire in ~7 real seconds | — |
| Ali | one claim in, one filing out, **on deployed infra** | — |

---

## Decisions log

Append here when something is settled, so nobody relitigates it at 2am.

- **10 Sep** — Storage goes through `core.db`, never `core.store` directly. Backend is `PANCHAYAT_BACKEND`.
- **10 Sep** — Everyone develops against the in-memory backend. Same tests must pass on both.
- **10 Sep** — Agent stack versions pinned. Raise in group before bumping.
- **10 Sep** — Branch protection is a git hook, not a GitHub ruleset (not enforced on private free-plan repos).
- **10 Sep** — `core/store.py` is real. `PANCHAYAT_BACKEND=dynamodb` works; set
  `PANCHAYAT_DDB_ENDPOINT=http://localhost:8000` to run it against DynamoDB
  Local. Nothing else changes -- keep importing `core.db`.
- **10 Sep** — **`store.reset()` refuses a non-local endpoint.** It deletes
  every row and `conftest.py` calls it twice per test, so
  `PANCHAYAT_BACKEND=dynamodb pytest` without a local endpoint was silently
  emptying the shared table. Set `PANCHAYAT_ALLOW_DESTRUCTIVE_RESET=yes` only
  if you mean it.
- **10 Sep** — Two index row types added that the schema table does not list:
  `FEEDER#<feeder>#SVC#<svc>` for `recurrence_count`, and a `GRANT#<grant_id>`
  pointer for `revoke_consent`. Neither query is answerable without a Scan
  otherwise. No new GSI. **Raised for review in PR #1, not settled.**
- **10 Sep** — `requirements.txt` needs **Python >= 3.12**: `numpy>=2.5.3`
  refuses to install on 3.11. If your venv is 3.11 you are blocked.
- **10 Sep** — Open bug, nobody's lane yet: `split_case` rebuilds a child's
  claims only from `merged_from`, so a case's FOUNDING household splits into a
  child with no claims. `core/memstore.py:95` has it too, so it must be fixed
  in both or the backends diverge.
- **10 Sep** — `test_virtual_clock_compresses_a_statutory_week` fails 5/5 on
  clean `f59598a` with only the stubs. It compares `start + 7 days` against a
  LATER `clock.now()`, and at scale 86400 even ~40us between the calls is ~3.4
  virtual seconds, so `.days` floors to 6. Raghav's lane.
- **10 Sep** — `ruff check .` is not clean repo-wide: 70 errors, 57 outside the
  mesh lane (`core/types.py` 18, `scripts/scaffold_stubs.py` 16,
  `core/clock.py` 9, `core/fakes.py` 8, `core/memstore.py` 4).
