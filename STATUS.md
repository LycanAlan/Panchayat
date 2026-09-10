# Status board

**Update your row when something lands. Takes ten seconds.**

This is not project-management theatre. Each of you has a separate Claude
session that cannot see the others. When Raghav's Claude reads this file it
learns that `store.py` is real and what shape it landed in, instead of guessing
or rebuilding it. That is the whole point.

Last updated: **10 Sep, 21:10** by Ali

---

## Blockers right now

| Blocker | Who it stops | Workaround in place | Owner |
|---|---|---|---|
| **Bedrock MODEL calls not authorised** (account flag, support case 178898467100367) | anything invoking a model | `core/models.py` seam: `PANCHAYAT_MODEL=anthropic` + an API key swaps provider in one env var. **AgentCore itself is LIVE** — the deploy target was never blocked. | Ali |
| Collaborators not invited | Kartik, Alakshendra, Raghav cannot clone | — | Ali |
| ~~`test_virtual_clock_compresses_a_statutory_week` fails 5/5~~ | — | **FIXED 10 Sep by Ali.** See note below. | closed |
| **`case.escalation_tier` has two potential writers, no locking** -- Kartik's ambient `apply_upgrade()` and Raghav's `climb()` both read-modify-write it, and `put_case()` is a blind overwrite. Lost update or a double-escalation (files at the wrong tier/authority) are both real. Needs a decision: `climb()` as sole writer with `apply_upgrade` requesting rather than performing, or a conditional write on a version attribute. Same shape as the `put_case` stale-write hazard in Kartik's review -- likely one fix for both. | escalation correctness | none yet -- `climb()` writes the tier it read, does not attempt to resolve the race | Raghav + Kartik |
| **No signing mechanism exists for ANY escalation tier, not just 1-3** -- Alakshendra asked whether tiers 1-3 auto-filing with no signature is intentional (sign once at intake) or a gap. Checked: `climb()` never sets `Filing.signed_by` for any tier, including tier 1. His `institutions/client.py` (branch `alakshendra/ladder-and-filing-client`, unmerged) already enforces hard rule 4 in `file()` -- an empty `signed_by` returns `Outcome.NEEDS_HUMAN` rather than filing. So once wired, every tier fails NEEDS_HUMAN forever, always, until something captures a household member's approval onto the `Filing` before `climb()` submits. Not a policy question (per-tier vs once) -- the capture step doesn't exist anywhere yet. Likely lands in Ali's `agents/digest.py` ("pings you when there's a real decision"). Separately: `submit`'s `bool` contract can't represent `DeskReply`'s outcome space -- `should_retry` is true only for `UNREACHABLE`, while `REJECTED` sets `should_pause_sla` but needs a human to supply missing particulars, not a blind resend. `climb()`'s current retry-twice logic would mishandle `REJECTED` once real replies flow through. Documented in code at the call site in `agents/watchdog.py::climb()`. | filing correctness once institutions/ merges | none -- `climb()` submits with `signed_by=None` always; harmless today only because the default `submit` stub is unconditional `True` | Raghav + Alakshendra + Ali |

**On that clock test** — Alakshendra's diagnosis was right and it is fixed.
Worth knowing why it passed here and failed there: Windows' `monotonic()` has
15.625ms resolution, so both `now()` calls usually land in the SAME tick and the
drift is exactly zero. On a finer clock it never is. The assertion was really
testing the platform's timer. It now asserts the gap corresponds to under a
second of REAL elapsed time, which is stable everywhere.

**Good catch, and the right call to flag rather than edit.** That is exactly
what STATUS.md is for.

---

## Lane status

| Lane | Module | State | Notes |
|---|---|---|---|
| **shared** | `core/types.py` | **DONE, FROZEN** | Raise changes in the group |
| **shared** | `core/clock.py` | **DONE** | Real + virtual, one code path |
| **shared** | `core/memstore.py` | **DONE** | In-memory, full interface |
| **shared** | `core/db.py` | **DONE** | The seam. Import from here. Missing backend fns now raise by name instead of binding `None`. |
| **shared** | `core/fakes.py` | **DONE** | `the_outage()` has 12 claims + a decoy |
| **shared** | `tests/` | **DONE** | **58 passing**, no AWS needed |
| Kartik | `core/store.py` | not started | DynamoDB. Must pass `tests/test_contract.py`. |
| Kartik | `core/scoring.py` | not started | |
| Kartik | `agents/pattern_watch.py` | not started | |
| Kartik | `agents/anti_abuse.py` | not started | |
| Alakshendra | `data/jurisdiction/ward12.yaml` | **DONE** | 31 entries. Water only. 24 BWSSB, 3 BBMP borewell, 3 builder line. **Sample can now be deleted** — see decisions log. |
| Alakshendra | `agents/remedy.py` | **DONE** | `lookup(service, segment, feeder_id)` and `resolve(claim) -> (tail, entry, citation)`. Returns `None` on a miss, never a guess. |
| Alakshendra | `institutions/` | **DONE** | 5 desks, one implementation. `python -m institutions.server bwssb`. Ports 9001-9005, agent cards verified. |
| Raghav | `core/clock.py` | **DONE** (on `feat/household-time`, in review) | Naive-UTC helper + `asyncio.get_running_loop()` fix. Kept main's memoised `get_clock()` through the rebase. |
| Raghav | `agents/intake.py` | **DONE** (on `feat/household-time`, in review) | `parse()`/`read_back()`, injectable model, no AWS creds needed to test |
| Raghav | `agents/household.py` | **DONE** (on `feat/household-time`, in review) | `build_swarm()`/`deliberate()`, dialysis fixture surfaces the elder's unstated deadline |
| Raghav | `agents/warden.py` | **DONE** (on `feat/household-time`, in review) | `minimise()`, `consent_covers()`, `check_inference_leak()` -- all adversarially tested |
| Raghav | `agents/watchdog.py` | **DONE** (on `feat/household-time`, in review) | `reconcile_closure()`, `climb()`, dispatch, `withdraw()`. **Review blocker B1 fixed** — closure check now looks backward over a `closure_lookback_days` window (default 7, matching `sla_days`), was looking forward and could never fire. |
| Ali | `graph/request_path.py` | **DONE (spine)** | Runs end to end on stubs, no AWS, no model. `run_request_path(payload)`. |
| Ali | `agents/digest.py` | not started | |
| Ali | AgentCore deploy | not started | **do this Day 2, not Day 4** |
| Ali | `graph/trace.py` | **DONE** | `CaseTrace`. The demo surface, built with the spine not after it. |
| Ali | `core/models.py` | **DONE** | Model seam. `get_model("reason"|"cheap")`. Never hardcode a model ID. |
| Ali | trace UI | not started | |

---

## Day 1 gates — report the result, not the vibe

| Who | Gate | Result |
|---|---|---|
| Alakshendra | 50 labelled complaints routed, **target ≥80%** | **PASSED — 47/50, 94%.** Correct body 92%, declined-to-guess 14/14. `python -m eval.routing_accuracy` |
| Kartik | `store.py` passes `tests/test_contract.py` on DynamoDB | — |
| Raghav | `test_clock.py` proves 7 virtual days fire in ~7 real seconds | **PASSED.** Whole lane green, no AWS creds. 1 honest skip (`strands` not installed locally). |
| Ali | one claim in, one filing out, **on deployed infra** | **PARTIAL — passes locally.** `pytest tests/test_request_path.py`, 8/8. Routes to BWSSB with a real citation through Alakshendra's table. Deploy still pending. |

---

## Decisions log

Append here when something is settled, so nobody relitigates it at 2am.

- **10 Sep** — Storage goes through `core.db`, never `core.store` directly. Backend is `PANCHAYAT_BACKEND`.
- **10 Sep** — Everyone develops against the in-memory backend. Same tests must pass on both.
- **10 Sep** — Agent stack versions pinned. Raise in group before bumping.
- **10 Sep** — Branch protection is a git hook, not a GitHub ruleset (not enforced on private free-plan repos).
- **10 Sep** — `agents/remedy.load_table()` skips `*.sample.yaml`. The sample duplicates two segments and adds a garbage entry that is out of scope, and a real filing must never go out backed by scaffolding. `ward12.sample.yaml` is now safe to delete whenever Kartik and Raghav confirm nothing local still loads it — the loader already ignores it either way.
- **10 Sep** — `ward12-9thmain` is curated into the real table because `core.fakes.the_outage()` uses it as the decoy. The fixture keeps working after the sample file goes.
- **10 Sep** — The jurisdiction table is **water only**, per the Day 1 brief: one ward deep beats five wards shallow. A garbage or pothole complaint therefore resolves to nothing and the Remedy Agent says so and asks. That is the designed answer, not a gap — `eval/routing_accuracy.py` scores declining as correct.
- **10 Sep** — The table deliberately answers three different authorities. If every segment answered BWSSB, a stub returning the string would score 100% on the routing gate.
- **10 Sep** — The request spine is wired with every node stubbed rather than waiting for agents. Nodes call the real implementation and fall back **only** on `NotImplementedError`, marking the trace `(STUB)`. Any other exception fails loudly: canned data that hides a teammate's bug is worse than a red run. Your stub marker disappears the moment your module lands — no rewiring, no `if demo_mode:`.
- **10 Sep** — Per-request state travels in Strands' `invocation_state`, not a module global. Two households reporting at once must not write into each other's case.
- **10 Sep** — Models go through `core/models.py`. Never construct a `BedrockModel` in an agent file and never hardcode a model ID — Claude 3.5 is EOL and is exactly what gets copied off a blog post. `us-east-1`, because **ap-south-1 has no Anthropic inference profiles at all**.
- **10 Sep** — A missing embedding makes the semantic term **unavailable, not zero**. Scored as zero the ceiling is 0.65 against TAU 0.72, so two houses on one trunk main reporting the same fault a minute apart would never cluster, silently. Renormalise over the weights that ran; see CLAUDE.md.
- **10 Sep** — Embedding does **not** happen in `put_claim()`. Both db backends must match, so that puts a Bedrock call in the offline suite. It belongs in the ambient Pattern Watch pass.
