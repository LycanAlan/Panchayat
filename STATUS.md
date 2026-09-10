# Status board

**Update your row when something lands. Takes ten seconds.**

This is not project-management theatre. Each of you has a separate Claude
session that cannot see the others. When Raghav's Claude reads this file it
learns that `store.py` is real and what shape it landed in, instead of guessing
or rebuilding it. That is the whole point.

Last updated: **10 Sep, 21:42** by Alakshendra

---

## Blockers right now

| Blocker | Who it stops | Workaround in place | Owner |
|---|---|---|---|
| **Bedrock MODEL calls not authorised** (account flag, support case 178898467100367) | anything invoking a model | `core/models.py` seam: `PANCHAYAT_MODEL=anthropic` + an API key swaps provider in one env var. **AgentCore itself is LIVE** — the deploy target was never blocked. | Ali |
| Collaborators not invited | Kartik, Alakshendra, Raghav cannot clone | — | Ali |
| ~~`test_virtual_clock_compresses_a_statutory_week` fails 5/5~~ | — | **FIXED 10 Sep by Ali.** See note below. | closed |

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
| **shared** | `tests/` | **DONE** | **99 passing**, no AWS needed |
| Kartik | `core/store.py` | not started | DynamoDB. Must pass `tests/test_contract.py`. |
| Kartik | `core/scoring.py` | not started | |
| Kartik | `agents/pattern_watch.py` | not started | |
| Kartik | `agents/anti_abuse.py` | not started | |
| Alakshendra | `data/jurisdiction/ward12.yaml` | **DONE** | 31 entries. Water only. 24 BWSSB, 3 BBMP borewell, 3 builder line. **Sample can now be deleted** — see decisions log. |
| Alakshendra | `agents/remedy.py` | **DONE** | `lookup(service, segment, feeder_id)` and `resolve(claim) -> (tail, entry, citation)`. Returns `None` on a miss, never a guess. |
| Alakshendra | `institutions/` | **DONE** | 5 desks, one implementation. `python -m institutions.server bwssb`. Ports 9001-9005. Now on `core.models.get_model("cheap")` — a desk picking a tool is classification, not deliberation. |
| Alakshendra | escalation ladder API | **DONE** | **Raghav: `climb()` is unblocked.** `remedy.next_step(entry, tier)` -> the next `EscalationStep`, or `None` when exhausted. `institutions.routing.desk_for(step.authority)` -> which desk, or why there is none. |
| Alakshendra | `institutions/client.py` | **DONE** | **Ali: filing is unblocked.** `build_filing_tool()` gives you a Strands `@tool` for a graph node. Works offline — no desk listening returns UNREACHABLE, never raises. |
| Alakshendra | `institutions/protocol.py` | **DONE** | Shared wire grammar `OUTCOME [ref][: detail]`. Use `DeskReply.filed` / `.should_pause_sla` / `.needs_human` instead of string matching. |
| Alakshendra | `core/tags.py` | **DONE, proposed** | Structured tags: `emit(Tag.LADDER, "climbed", case_id=...)`. **Ali — if the trace UI wants a different shape, say so and it moves.** |
| Raghav | `agents/intake.py` | not started | |
| Raghav | `agents/household.py` | not started | |
| Raghav | `agents/warden.py` | not started | |
| Raghav | `agents/watchdog.py` | not started | |
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
| Raghav | `test_clock.py` proves 7 virtual days fire in ~7 real seconds | — |
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
- **10 Sep** — Authority-to-desk is its own curated table (`institutions/routing.yaml`), not a field on `EscalationStep`. Keeps `core/types.py` frozen and keeps "which office answers" the same kind of curated fact as "who is responsible". Matching is whole-word: a substring match put `RTI` inside `certification` and routed an ordinary ward filing to the never-file rule.
- **10 Sep** — Desks return a typed `DeskReply`, not a string. Three callers were going to parse that text and one of them would have got it wrong. **`should_pause_sla` is the one to respect** — never run a statutory clock against a filing that never landed.
- **10 Sep** — `NEEDS_HUMAN` is distinct from `REJECTED`. A rejection means resubmit with the missing particulars; NEEDS_HUMAN means no desk exists and retrying can never help. Tier 4 RTI is the case: drafted, never filed.
- **10 Sep** — `A2AServer(host=...)` is the BIND address and the agent card advertises it; an A2A client dials whatever the card says. Binding `0.0.0.0` published `http://0.0.0.0:9002/` and every call died with `ConnectError` that read like the desk being down. Desks now bind broadly and advertise `PANCHAYAT_PUBLIC_HOST` (default `localhost`). **Anyone standing up a new A2A server: set `http_url`.**
