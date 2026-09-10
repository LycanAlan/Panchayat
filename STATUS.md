# Status board

**Update your row when something lands. Takes ten seconds.**

This is not project-management theatre. Each of you has a separate Claude
session that cannot see the others. When Raghav's Claude reads this file it
learns that `store.py` is real and what shape it landed in, instead of guessing
or rebuilding it. That is the whole point.

Last updated: **10 Sep, 15:00** by Ali

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
| Kartik | `core/store.py` | not started | DynamoDB. Must pass `tests/test_contract.py`. |
| Kartik | `core/scoring.py` | not started | |
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
| Kartik | `store.py` passes `tests/test_contract.py` on DynamoDB | — |
| Raghav | `test_clock.py` proves 7 virtual days fire in ~7 real seconds | — |
| Ali | one claim in, one filing out, **on deployed infra** | — |

---

## Decisions log

Append here when something is settled, so nobody relitigates it at 2am.

- **10 Sep** — Storage goes through `core.db`, never `core.store` directly. Backend is `PANCHAYAT_BACKEND`.
- **10 Sep** — Everyone develops against the in-memory backend. Same tests must pass on both.
- **10 Sep** — Agent stack versions pinned. Raise in group before bumping.
- **10 Sep** — Branch protection is a git hook, not a GitHub ruleset (not enforced on private free-plan repos).
