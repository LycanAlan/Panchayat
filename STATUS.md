# Status board

**Update your row when something lands. Takes ten seconds.**

This is not project-management theatre. Each of you has a separate Claude
session that cannot see the others. When Raghav's Claude reads this file it
learns that `store.py` is real and what shape it landed in, instead of guessing
or rebuilding it. That is the whole point.

Last updated: **11 Sep, 02:40** by Kartik

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
| **shared** | `tests/` | **DONE** | **114 passing / 23 skipped** on memory, **137 passing** on dynamodb. No AWS needed. |
| Kartik | `core/store.py` | **DONE, REVIEWED** | DynamoDB, 17 fns. All 5 review findings fixed. Membership writes are narrow + conditional + transactional, so ambient can no longer clobber the Watchdog's breach. Verified on DynamoDB Local, **not yet the real table**. |
| Kartik | `core/scoring.py` | **DONE, REVIEWED** | `correlate()` renormalises when semantic is absent. `semantic_score()` is **gone** -- use `cosine()`, which returns `None`. `embed()` written but never executed. |
| Kartik | `eval/tau_sweep.py` | **DONE** | `python -m eval.tau_sweep`. Sweeps both scoring regimes. Numbers under D3 below. |
| Kartik | `tests/test_store_pure.py` | **DONE** | 24 tests, no AWS, runs on every offline `pytest` |
| Kartik | `tests/test_store_dynamodb.py` | **DONE** | 23 tests, skipped unless `PANCHAYAT_BACKEND=dynamodb` |
| Kartik | `agents/pattern_watch.py` | not started | |
| Kartik | `agents/anti_abuse.py` | not started | |
| Alakshendra | `data/jurisdiction/ward12.yaml` | **DONE** | 31 entries. Water only. 24 BWSSB, 3 BBMP borewell, 3 builder line. **Sample can now be deleted** — see decisions log. |
| Alakshendra | `agents/remedy.py` | **DONE** | `lookup(service, segment, feeder_id)` and `resolve(claim) -> (tail, entry, citation)`. Returns `None` on a miss, never a guess. |
| Alakshendra | `institutions/` | **DONE** | 5 desks, one implementation. `python -m institutions.server bwssb`. Ports 9001-9005, agent cards verified. |
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
| Kartik | `store.py` passes `tests/test_contract.py` on DynamoDB | **PASS, same caveat.** After merging main: **137 passed** on dynamodb, **114 passed / 23 skipped** on memory, zero failures either way. Still **DynamoDB Local**, not our table -- no AWS credentials here. Re-run when they land. |
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
- **10 Sep** — `core/store.py` is real. `PANCHAYAT_BACKEND=dynamodb` works; set
  `PANCHAYAT_DDB_ENDPOINT=http://localhost:8000` to run it against DynamoDB
  Local. Nothing else changes -- keep importing `core.db`.
- **10 Sep** — **`store.reset()` refuses a non-local endpoint.** It deletes
  every row and `conftest.py` calls it twice per test, so
  `PANCHAYAT_BACKEND=dynamodb pytest` without a local endpoint was silently
  emptying the shared table. Set `PANCHAYAT_ALLOW_DESTRUCTIVE_RESET=yes` only
  if you mean it.
- **11 Sep** — **SETTLED (Ali, review D2).** The two extra index row types are
  approved: `FEEDER#<f>#SVC#<svc>` for `recurrence_count` and `GRANT#<id>`
  for `revoke_consent`, plus uniquifiers on the consent and disclosure sort
  keys. Neither adds a GSI, neither changes a declared entity key. Now written
  into the schema table in `docs/team/KARTIK.md`.
- **10 Sep** — `requirements.txt` needs **Python >= 3.12**: `numpy>=2.5.3`
  refuses to install on 3.11. If your venv is 3.11 you are blocked.
- **10 Sep** — Open bug, nobody's lane yet: `split_case` rebuilds a child's
  claims only from `merged_from`, so a case's FOUNDING household splits into a
  child with no claims. `core/memstore.py:95` has it too, so it must be fixed
  in both or the backends diverge.
- **10 Sep** — ~~`test_virtual_clock_compresses_a_statutory_week` fails 5/5~~
  **FIXED by Ali in `0befb9b`.** It compared `start + 7 days` against a LATER
  `clock.now()`, and at scale 86400 even ~40us between the calls is ~3.4
  virtual seconds, so `.days` floored to 6. The suite is now green on both
  backends with nothing skipped that should run.
- **10 Sep** — `ruff check .` is not clean repo-wide: 70 errors, 57 outside the
  mesh lane (`core/types.py` 18, `scripts/scaffold_stubs.py` 16,
  `core/clock.py` 9, `core/fakes.py` 8, `core/memstore.py` 4).
- **11 Sep** — **`scoring.semantic_score()` is deleted.** It collapsed
  "could not compute" to a bare `0.0`, which folded into the weighted sum caps
  every score at 0.65 and puts it under TAU forever. Use **`cosine(a, b)`**,
  which returns `None` when the term is unavailable. If you want the answer
  `correlate()` uses, call `correlate()`.
- **11 Sep** — **`RECENCY_HALFLIFE_HOURS` is now `RECENCY_DECAY_HOURS`.**
  `exp(-d/H)` halves at `H*ln2 = 33.3h`, not at 48h. Same arithmetic, honest
  name. Asked for "a 24h half-life" you would have set 24.0 and got 16.6h.
- **11 Sep** — **A NaN cosine used to read as PERFECT agreement.**
  `min(1.0, nan)` is `1.0` in Python, and `pack_embedding` overflows to `inf`
  above 65504, so a vector that could not survive storage came back out as
  semantic agreement flagged as computed. Fixed in `cosine()`. If you are
  writing anything that scores vectors, guard `np.isfinite` on the **result**
  as well as the inputs -- 1e200 is finite and its square is not.
- **11 Sep** — **Case writes are no longer whole-item puts.**
  `add_household_to_case` and `split_case` write only `household_ids`,
  `claim_ids` and `merged_from`, conditionally, with a retry, in one
  transaction with the member row. If you write a Case from the ambient or
  temporal path, **do not** read-modify-write the whole item: the Watchdog owns
  `status` and `sla_deadline` and a full put takes its breach back out with
  nothing logged.
- **11 Sep** — `open_cases()` now returns **oldest first** on dynamodb.
  memstore still returns insertion order; it needs the same sort to agree.
  Ali's call, `core/memstore.py` is shared.
- **11 Sep** — **D3 has numbers, and it needs a group call.**
  `python -m eval.tau_sweep`. TAU = 0.72 is not the right threshold for either
  scoring path: the renormalised one wants **0.78** (all three semantic models,
  zero missed clusters, under a 1% false-merge ceiling). Turning semantic on
  costs 0.8% / 5.9% / 17.6% of same-fault pairs depending on how much a real
  cosine separates the classes -- and **zero** pairs ever start clustering, so
  the regression is one-way. Proposal, backed by Ali: `TAU_TOPOLOGICAL` and
  `TAU_FULL`, swept separately, with the trace naming which one applied.
- **11 Sep** — **Open, nobody's lane: segment normalisation stops at the
  scorer.** `topology_score` now normalises case and whitespace, but
  `claims_in_window` builds `GSI1PK` from the raw `claim.segment`, so
  `Ward12-4thCross` and `ward12-4thcross` land in different partitions and
  Pattern Watch never retrieves the pair to score at all. Same bug one layer
  down. Needs normalising **on the way in** (intake or the Warden, before a
  `Claim` is emitted), or agreed as a rule both backends apply at the key --
  fixing it in `store.py` alone breaks backend parity.
- **11 Sep** — `scripts/create_table.py` exists. Idempotent, reads
  `PANCHAYAT_TABLE` and `PANCHAYAT_DDB_ENDPOINT`, carries the full key table in
  its docstring. Ali's lane; there because he asked for it in review D4.
