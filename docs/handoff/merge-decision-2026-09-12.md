# Merge decision — 12 Sep, picked up mid-audit

Quick note, session ended here. Ali's session, after verifying Raghav's audit.

## Recommendation: MERGE, in this order

`main` has **not** moved (still `96215ae`). All five branches are still open.

| # | Branch | Note |
|---|---|---|
| 1 | `feat/plat-deploy-readiness` (#6) | platform |
| 2 | `alakshendra/day3-institutions` (#5) | institutions |
| 3 | `feat/mesh-density-harness` (#22) | **strictly contains `feat/mesh-day3` (#8)** — merge this one, not both |
| 4 | `feat/hh-closure-evidence` | **supersedes `feat/hh-watchdog-pause-path` (#7)** — Raghav stacked his two fixes on top of it. Merge this, close #7. |

Only `STATUS.md` conflicts, both sides appending. No code conflicts.

Expect **2 failures, both deliberate canaries**, neither a regression:

- `test_a_failed_filing_currently_freezes_the_case_permanently` — Alakshendra's.
  His docstring says to delete it when the pause path schedules a retry. It does now.
- `test_the_shipped_rule_disputes_a_case_using_its_own_founding_claims` — Kartik's.
  Its own failure message says the shipped rule stopped disputing. Raghav's fix landed.

**Each owner deletes/updates their own. Do not "fix" the code to make them pass.**

## Verified independently (not taken on report)

- Raghav's `reconcile_closure` fix: own founding claims → **not disputed**;
  a neighbouring household → **still disputed**. The demo's peak moment is intact.
- His branch contains Ali's three commits plus his two.

## THE OPEN DECISION — Ali's, and it is not cosmetic

`graph/request_path.py::_household` line 161:

```python
need = (ctx.payload.get("needs") or [{}])[0]
```

Raghav fixed intake's half (empty text → `[]` needs) and left this deliberately,
with a note in his code rather than reaching into the file.

**Measured on his branch: his fix currently changes nothing end to end.**
A report with `text=""` still produces:

```
SIGNAL      intake   | 0 need(s) from en text     <- his fix working
...
DRAFTED     file     | BWSSB Assistant Engineer, sub-division office, tier 1
filings: 1
```

An empty report still drafts a tier-1 filing against a **named officer** with an
empty body. Hard rule 4 holds (nothing is submitted), but nothing should be
drafted either.

**Decide before merging, or merge and fix immediately after — but do not
consider the empty-report hole closed. It is not.**

Suggested shape (untried): `_household` short-circuits on zero needs the way
`run_request_path` already refuses a missing `segment` — HELD trace line plus an
`unrouted_reason` of `"no_need"`, reusing the `_response(ctx)` path that exists.
The graph edges are linear (`intake → household → warden → remedy → file`), so
stopping cleanly needs either an edge condition or an early return in
`run_request_path`. Not attempted.

## Also still open (unchanged from yesterday)

- **`check_closure` is never scheduled anywhere.** Raghav grepped every
  `clock.schedule()`. The disputed-closure moment — the whole video — can only
  fire from tests and Kartik's harness. He calls this the biggest thing left and
  deliberately did not invent a polling cadence alone. **Needs the group.**
- **No signature capture for any tier** → every filing returns `NEEDS_HUMAN`
  once the real adapter is installed.
- **`stalled_cases()` missing from `core/store.py`** (memstore has it) — raises
  on a real DynamoDB deploy the moment the digest wires it up.
- **`escalation_tier` has two writers**, no version guard.
- **AgentCore image never built, nothing deployed.**

## One correction Raghav caught in his own tooling

An automated review reported a dual-`@app.entrypoint` deploy blocker in
`app.py`. **False positive** — it misread the explanatory comment
`# NOT @app.entrypoint` as code. Verified at runtime: one handler,
`{'main': invoke}`. Worth knowing so it does not resurface.
