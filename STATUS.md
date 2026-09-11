# Status board

**Update your row when something lands. Takes ten seconds.**

This is not project-management theatre. Each of you has a separate Claude
session that cannot see the others. When Raghav's Claude reads this file it
learns that `store.py` is real and what shape it landed in, instead of guessing
or rebuilding it. That is the whole point.

Last updated: **11 Sep, 16:25** by Alakshendra
Last updated: **11 Sep, 04:15** by Kartik

---

## Blockers right now

| Blocker | Who it stops | Workaround in place | Owner |
|---|---|---|---|
| **Bedrock MODEL calls not authorised** (account flag, support case 178898467100367) | anything invoking a model | `core/models.py` seam: `PANCHAYAT_MODEL=anthropic` + an API key swaps provider in one env var. **AgentCore itself is LIVE** — the deploy target was never blocked. | Ali |
| Collaborators not invited | Kartik, Alakshendra, Raghav cannot clone | — | Ali |
| ~~`test_virtual_clock_compresses_a_statutory_week` fails 5/5~~ | — | **FIXED 10 Sep by Ali.** See note below. | closed |
| ~~`Watchdog.climb()`'s `submit` seam and `institutions.client`'s filer have different shapes~~ | — | **CLOSED Day 3.** `institutions.client.build_submit()`. See the note below — the collapse rule I originally proposed in this file was wrong and would have defeated hard rule 4. | Alakshendra |
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

**On the `submit` seam** — checked `feat/household-time`'s `watchdog.py`
against my just-reviewed `institutions/client.py` while looking for anything
that might already be calling it (nothing does yet, so no live breakage). Two
things, neither of them a criticism of either branch — both were built
correctly against their own contract, they just haven't met yet:

1. **Shape.** `Watchdog.climb()` takes `submit: Callable[[Filing], bool]` — one
   `Filing` in, `True`/`False` out. `InstitutionClient.file_for_authority()`
   takes five separate arguments (`authority, case_id, service, body,
   idempotency_key, signed_by`) and returns a `DeskReply` — a richer type on
   purpose (`.should_pause_sla`, `.needs_human`, `.needs_resubmission` are
   distinct properties, not one boolean). Plugging one straight into the other
   won't type-check, and a lambda that forces it to fit **loses the
   distinction the whole review pass just built**: a `REJECTED` and an
   `UNREACHABLE` would both collapse to `False`, and the Watchdog can no
   longer tell "needs a human to fix something" from "just retry it."
   Proposing a small adapter — `Filing -> DeskReply.should_pause_sla is False`
   as the bool, with the full `DeskReply` still available to whoever wires it
   for the richer branching. Whoever lands the wiring, ping the other first —
   five-minute conversation, not a blocker.

   > **CORRECTION, Day 3 — the rule proposed above is wrong. Do not use it.**
   > `should_pause_sla is False` returns **True for NEEDS_HUMAN**, and
   > NEEDS_HUMAN is what hard rule 4 returns for an unsigned filing, which
   > today is *every* filing. The adapter would have reported each one as
   > successfully filed, advanced the tier and started a statutory clock
   > against a submission that never left the building — defeating rule 4
   > at the exact seam built to enforce it. It also diverges wrongly on
   > CLOSED, OPEN and UNKNOWN. **The shipped rule is `reply.filed`**, true
   > only when a ticket exists on the other side. Ali caught this; the table
   > of all eight outcomes is in `build_submit()`'s docstring.
   >
   > Nothing is lost to the bool: the adapter writes the desk's reference and
   > rendered reply onto the `Filing` (`external_ref`, `response`,
   > `submitted_at`), and `climb()` persists it with `put_filing_once()` on
   > the next line.
   >
   > **One thing for Raghav, flagged not edited.** With the real adapter
   > wired, an unsigned filing now traces as
   > `PAUSED watchdog -> endpoint unreachable, clock held`. The pause is
   > correct; the wording is not — nothing was unreachable, the filing was
   > refused for having no signer and never left the process. The structured
   > tag beside it is accurate (`tag=filing event=submitted outcome=NEEDS_HUMAN
   > needs_human=True`), so the information is there, but the human-readable
   > line in `climb()` will send someone hunting a network problem on Day 4.
   > Your file, your call.
2. **`signed_by`.** `file()` now refuses anything with an empty `signed_by`
   (hard rule 4, from Ali's review — see `docs/review/inst-ladder-filing.md`
   B1). `climb()`'s `Filing(...)` for tiers 1-3 doesn't set one. Genuine
   question, not a bug report: is that intentional (household signs once at
   the initial filing, the ladder auto-continues on that authorization) or
   should every escalation tier need its own fresh sign-off, same as tier 4's
   RTI? Ali's review of this same branch raised the retry-count question on
   `climb()`'s `submit` call right next to this, so worth answering both at
   once.

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
| Alakshendra | `institutions/` | **DONE** | 5 desks, one implementation. `python -m institutions.server bwssb`. Ports 9001-9005. Now on `core.models.get_model("cheap")` — a desk picking a tool is classification, not deliberation. |
| Alakshendra | escalation ladder API | **DONE** | **Raghav: `climb()` is unblocked.** `remedy.next_step(entry, tier)` -> the next `EscalationStep`, or `None` when exhausted. `institutions.routing.desk_for(step.authority)` -> which desk, or why there is none. |
| Alakshendra | `institutions/client.py` | **DONE, reviewed** | **Ali: filing is unblocked.** `build_filing_tool()` gives you a Strands `@tool` for a graph node. Works offline — no desk listening returns UNREACHABLE, never raises. Two blockers from Ali's review (unsigned filings, household text in instruction position) fixed — see `docs/review/inst-ladder-filing.md`. **Not yet wired to `Watchdog.climb()`'s `submit` seam — see blocker row above.** |
| Alakshendra | `institutions/protocol.py` | **DONE** | Shared wire grammar `OUTCOME [ref][: detail]`. Use `DeskReply.filed` / `.should_pause_sla` / `.needs_human` instead of string matching. |
| ~~Alakshendra~~ → **Ali** | `core/tags.py` | **HANDED OVER, Day 3** | Ownership moved to platform as agreed. Four lanes emit through it; the OTEL span work and the trace UI are what decide its shape, and both are yours. Change it here, not at the call sites. |
| Alakshendra | `remedy.lookup()` cache | **FIXED, Day 3** | **Was the blocking item.** `lookup()` and `load_table()` returned the cached objects themselves, so one caller emptying a ladder stalled `climb()` process-wide — invisibly, because the next lookup still succeeded and returned the corrupted row. Both now deep-copy (24µs). 4 regression tests, including one level down: mutating a `ladder[0]` step. |
| Alakshendra | `institutions.client.build_submit()` | **DONE, Day 3** | **The Watchdog seam is wired.** `build_submit(client=None, service="water") -> Callable[[Filing], bool]`. Lives in institutions/ so the temporal lane never imports it — there is a test asserting that. `tests/test_submit_adapter.py` drives a real `climb()` against a real client with only the desk's reply faked. |
| Alakshendra | `agents/remedy.compose_filing()` | **DONE** | `(case, entry, facts, step=None) -> (body, missing_fields)`. Turns `required_fields` + what we know into filing text, or refuses with what is missing rather than filing something the desk will bounce. `affected_count` auto-fills from `case.corroboration`. Tested end to end against `Desk.accept()`'s own completeness check, not just against expectations. |
| Raghav | `agents/intake.py` | not started | |
| Raghav | `agents/household.py` | not started | |
| Raghav | `agents/warden.py` | not started | |
| Raghav | `agents/watchdog.py` | not started | |
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
| Kartik | `store.py` passes `tests/test_contract.py` on DynamoDB | **PASS, same caveat.** After merging main: **137 passed** on dynamodb, **114 passed / 23 skipped** on memory, zero failures either way. Still **DynamoDB Local**, not our table -- no AWS credentials here. Re-run when they land. |
| Raghav | `test_clock.py` proves 7 virtual days fire in ~7 real seconds | — |
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
- **10 Sep** — Authority-to-desk is its own curated table (`institutions/routing.yaml`), not a field on `EscalationStep`. Keeps `core/types.py` frozen and keeps "which office answers" the same kind of curated fact as "who is responsible". Matching is whole-word: a substring match put `RTI` inside `certification` and routed an ordinary ward filing to the never-file rule.
- **10 Sep** — Desks return a typed `DeskReply`, not a string. Three callers were going to parse that text and one of them would have got it wrong. **`should_pause_sla` is the one to respect** — never run a statutory clock against a filing that never landed.
- **10 Sep** — `NEEDS_HUMAN` is distinct from `REJECTED`. A rejection means resubmit with the missing particulars; NEEDS_HUMAN means no desk exists and retrying can never help. Tier 4 RTI is the case: drafted, never filed.
- **10 Sep** — `A2AServer(host=...)` is the BIND address and the agent card advertises it; an A2A client dials whatever the card says. Binding `0.0.0.0` published `http://0.0.0.0:9002/` and every call died with `ConnectError` that read like the desk being down. Desks now bind broadly and advertise `PANCHAYAT_PUBLIC_HOST` (default `localhost`). **Anyone standing up a new A2A server: set `http_url`.**
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
  costs **0.7% / 8.4% / 22.0%** of same-fault pairs depending on how much a
  real cosine separates the classes -- and **zero** pairs ever start
  clustering, so the regression is one-way. Proposal, backed by Ali:
  `TAU_TOPOLOGICAL` and `TAU_FULL`, swept separately, with the trace naming
  which one applied.
  **CORRECTED 04:15** -- the first numbers posted (0.8/5.9/17.6%) came off a
  corpus whose street suffix was drawn at random rather than derived from the
  number, so one street appeared under several spellings and pairs physically
  on it scored 0 topology. The conclusion is unchanged and slightly stronger:
  the cost in the harder regimes was UNDER-stated.
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
- **11 Sep** — **`feeder_id` is normalised now, like `segment`.** Both fold
  through one `_norm()` in `core/scoring.py`. Compared byte-exact,
  `BWSSB-TM-14` and `bwssb-tm-14` scored topology **0.0** -- two houses on one
  trunk main renormalising to 0.385 and never clustering, through the field
  that carries four times the weight of the one that was already fixed.
- **11 Sep** — **A split child no longer files its own feeder index row.**
  `recurrence_count` answers "how many prior failures on this trunk main", and
  a split corrects how we grouped one rather than creating another. It was a
  ratchet: merge/split/merge/split climbed 1 -> 2 -> 3 -> 4 for one incident.
  The child now carries `split_from:<parent>` in `merged_from` (hard rule 6
  provenance) and the parent keeps the row. **`core/memstore.py` counts case
  records and needs the same exclusion to agree** -- shared file, raised not
  edited.
- **11 Sep** — **`revoke_consent` is conditional now.** `update_item` UPSERTS,
  so with a live pointer and a missing consent row it CREATED a stub carrying
  only `revoked_at`, returned True having marked nothing, and every later
  `live_consents()` for that household died on `KeyError: 'grant_id'`. It
  returns False instead. If you call it, check the return.
- **11 Sep** — `eval.tau_sweep`'s `best()` returns **None** when no threshold
  clears the false-merge ceiling, instead of falling back to one that violates
  it and printing it under the ceiling's own heading.
