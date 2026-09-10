# Review — `feat/mesh-day1`

Reviewed by Ali, 10 Sep, against the branch tip. **Every finding was reproduced
by executing your code in a worktree**, not inferred from reading it. Each one
has a paste-able reproduction — a review you cannot reproduce is an opinion.

Your suite is green on both backends and `ruff` is clean on your lane. None of
what follows is caught by the tests as written; that is the point of the pass,
not a criticism of the tests.

---

## Verdict

**Held on two, and one of them is a decision I owe you rather than a defect you
made.** The lane is in good shape — this is the most carefully verified branch
anyone has put up.

## Three things you got right that I want on the record

**You found a destructive bug before it destroyed anything.** `store.reset()`
scanning and deleting every row, called twice per test by a fixture, behind a
command three files advertise as supported — that is the worst class of bug in
the repo and you caught it in your own code, unprompted. The warning in your
summary was the correct instinct. **I checked: the shared table is intact**, and
the guard in `17b9588` refused when I ran it, so nothing was lost.

**The TAU transfer problem (your item 9) is the sharpest finding anyone has made
today, including me.** Verified your arithmetic:

```
renormalised   (0.40t + 0.25r) / 0.65        t=r=1 -> 1.00
full           0.40t + 0.25r + 0.35s         t=r=1 -> 0.65 + 0.35s
                                             needs s >= 0.2 to reach TAU 0.72
```

So a pair at `t=r=1, s=0.15` scores **1.00 today and 0.7025 the day Bedrock
unblocks** — below threshold. Turning embeddings on would *stop* pairs
clustering that cluster now. Nobody would have found that by reading the diff;
you found it by thinking about the regime change. See D3 below for the decision.

**Sixty checks against a live engine rather than assertions about your own
code**, and you reported that two of your own checks failed and were wrong. That
is how this should be done.

---

# Blockers

## B1 — The guard fixed a catastrophe by breaking the contract

```bash
PANCHAYAT_BACKEND=dynamodb pytest tests/test_time_discipline.py tests/test_scoring.py
# verified on your tip: 21 errors, all RuntimeError from reset()
```

Every test errors, **including tests that touch no storage at all**. That
command is the whole cross-backend model — it is in `CLAUDE.md`, in `README`,
and in `tests/test_contract.py`'s own docstring, and it is the mechanism that
proves memory and DynamoDB agree.

To be explicit: **the diagnosis was right and the remedy is wrong.** The bug is
not "reset was called against a remote endpoint"; it is that **an autouse
fixture calls a destructive operation at all** on a backend it does not own.
Refusing loudly is better than deleting, so this is an improvement — but it
trades a catastrophe for a broken contract, and we need neither.

That call is mine, not yours — `tests/conftest.py` and the seam are my files.
**D1, below.** Do not spend more time on it.

## B2 — A NaN cosine becomes perfect semantic agreement

```python
a = fakes.a_claim(embedding=[float("nan"), float("nan")])
b = fakes.a_claim(embedding=[1.0, 1.0], household_id="hh2")
s = scoring.correlate(a, b)
# verified: semantic=1.0  semantic_available=True  total=1.0
```

`min(1.0, nan)` returns `1.0` in Python, so the clamp converts "uncomputable"
into **fabricated perfect agreement, flagged as computed**. That is strictly
worse than the 0.65 ceiling this branch exists to remove: that failure was
silent and made us cluster too little, this one makes us cluster wrongly and
says it is sure.

It is reachable end to end through your own storage path:

```python
store.unpack_embedding(store.pack_embedding([70000.0, 1.0]))
# verified: [inf, 1.0]   (float16 max is 65504; RuntimeWarning only)
```

`inf` norm and `inf` dot give `inf/inf = nan`. Guard with
`np.isfinite(...).all()` and return `None` — the unavailable path you already
built is exactly right for it.

---

# Correctness

## C1 — Segment comparison is byte-exact, so case variants score zero

```python
x = fakes.a_claim(segment="ward12-4thcross", feeder_id="f1")
y = fakes.a_claim(segment="Ward12-4thCross", feeder_id="f2", household_id="h2")
scoring.topology_score(x, y)     # verified: 0.0   (should be 0.3)
scoring.topology_score(x, fakes.a_claim(segment=" ward12-4thcross ", feeder_id="f2"))  # 0.0
```

Normalisation lives inside `_parse_segment`, but line 71 compares raw strings
first. Two neighbours on one street whose intake text differed in casing get
**zero** topology and never corroborate. Normalise once at the top and compare
normalised forms.

## C2 — Read-modify-write on a Case, with three concurrent writers

`add_household_to_case`, `split_case` and `put_case` each do an unguarded
read-modify-write of the whole item on an eventually-consistent `GetItem`.
`CLAUDE.md` names three independent writers on one Case: the request Graph, the
ambient Streams Lambda, and the temporal Watchdog.

Ambient reads at `status=FILED`; the Watchdog concurrently writes
`status=BREACHED` with a new `sla_deadline`; ambient's `put_case` overwrites the
whole item and **the breach is gone, with nothing logged.** This cannot
reproduce on memstore — it mutates one shared object — which is precisely the
divergence class the seam exists to surface.

Needs a version attribute and a conditional write, or narrow `UpdateExpression`s
that touch only the fields each writer owns. Worth doing before Pattern Watch
starts mutating cases in flight.

## C3 — A bare-string service passes on memory and raises on DynamoDB

```python
db.put_claim(Claim(service="water"))
# memstore: fine.  dynamodb: AttributeError: 'str' object has no attribute 'value'
```

`_val`/`_svc` make every other key path tolerant, but `put_claim` routes through
`Claim.gsi1pk()`, which does `self.service.value`. Your own `_val` docstring
says it exists to catch exactly this. Build the claim's GSI1PK from
`_svc(claim.service)` here rather than from the frozen helper.

## C4 — `RECENCY_HALFLIFE_HOURS` is not a half-life

`exp(-delta/48)` halves at `48*ln2 = 33.3` hours, not 48. At 48h the score is
`0.368`, and `test_recency_decays_and_is_symmetric` pins that number, so the
misnomer is now load-bearing. Someone tuning "make the half-life 24h" sets
`24.0` and gets 16.6h, moving every score that feeds the TAU sweep. Rename to
`RECENCY_DECAY_HOURS`, or divide by `HALFLIFE/ln(2)`.

## C5 — `store.py` has no test that runs without AWS

632 lines, 17 functions, and the default `pytest` run selects memstore, so not
one line of it executes. `grep` finds no test importing `core.store`. Per B1 the
DynamoDB path cannot currently be run either, so **right now nothing exercises
this file in CI at all.**

The pure functions need no AWS and no Local: `pack_embedding`/`unpack_embedding`
round-trip, `_consent_sk` uniqueness, `_feeder_index_key`, `_claim_from`,
`_case_from`, `_reset_is_allowed`. Those alone would have caught B2's `inf`
round-trip. Your item 8 already proposes `tests/test_store_dynamodb.py` gated on
the backend — do that, and add a plain unit file for the pure half.

---

# Structural

**`put_case` pays a `GetItem` on every write** to clean up an index row whose
key it chose to make unstable. `graph/request_path.py` calls it once per request
with a brand-new `case_id`, so that read is a guaranteed miss on the hot path.
Key the index row on `case_id` alone — `PK='FEEDER#<f>#SVC#<s>'`,
`SK='CASE#<id>'` — and it is stable for the case's whole life: no orphan is
possible, the read disappears, and C2's stale-read hazard goes with it. That is
a better fix than the one you shipped for your finding 3.

**`open_cases` issues six GSI1 queries** (one per non-terminal status) and then
filters `service` in Python after all six are billed. It also returns
status-grouped order where memstore returns insertion order — a backend
divergence any `open_cases()[0]` caller will trip over.

**The `CASE#/HH#` member rows are written by two functions and read by none.**
`_claims_of` reads `merged_from` instead. Every merge pays an extra write for a
second copy of household→claims that nothing reconciles.

**`embed()` builds a boto3 client per call** — 100–300ms of session and
credential resolution per stream record, dwarfing the invoke. Module-level
`_client = None`, populated lazily inside `embed()`, keeps your "no client at
import" property and pays it once.

**`semantic_score` is still public and still collapses uncomputable to 0.0**,
with a docstring telling callers not to use it. `correlate` already bypasses it.
The next person to write `agents/pattern_watch.py` will reach for the public
name and reintroduce the 0.65 ceiling. Make the `Optional`-returning `_cosine`
the public API and delete the wrapper.

**`_reset_is_allowed` substring-matches the whole URL**, so
`http://localhost.example.com/` satisfies the guard. It also reads `ENDPOINT`
captured at import, so a test that sets `PANCHAYAT_DDB_ENDPOINT` afterwards
changes the verdict but not the cached table handle — the guard can approve one
endpoint while the wipe runs against another. Parse the host and compare it, and
read the env inside the function.

`_iso()` is dead — defined, never called.

---

# Decisions you asked for

## D1 — The conftest fixture (your item, B1 above). Mine, resolved.

The fixture will **skip reset entirely when the backend is not local**, rather
than erroring, and the DynamoDB gate will run against a dedicated table or
DynamoDB Local. Keep your guard in `reset()` — refusing a destructive call is
right regardless — but it stops being the thing the fixture trips over. I will
land this with my next platform push. **Nothing for you to do.**

## D2 — Your two new index row types (your item 2). Approved.

`FEEDER#<feeder>#SVC#<svc>` and the `GRANT#<id> -> household_id` pointer are
both fine. Neither adds a GSI, neither changes a declared entity key, and
neither query is answerable without a Scan otherwise — which is the bar. Write
them into the schema table in `CLAUDE.md` when you next touch it so they stop
being undocumented. **Same answer for your item 3**: uniquified consent and
disclosure sort keys are correct, and an append-only log that silently drops a
row is exactly the bug this table must not have.

## D3 — TAU across the regime change (your item 9). Needs a group call, not mine alone.

Your analysis is right and it is the most consequential open question in the
project. My reading: **two thresholds, swept independently**, because they are
genuinely two different scoring functions and pretending one number serves both
is how we end up with a demo that works and a system that does not.

Concretely — `TAU_TOPOLOGICAL` for the renormalised path and `TAU_FULL` for the
three-term path, each swept by `eval/tau_sweep.py`, with the trace naming which
one applied. That also makes the regime visible in the demo, which is honest:
while Bedrock is blocked, **every cluster we show forms without semantic
agreement** and we should say so rather than let it read as three-term scoring.

Bring it to the group with your numbers; I will back this version.

## D4 — Things of yours I am taking

- **`requirements.txt` is unsatisfiable on Python 3.11** (`numpy>=2.5.3` needs
  3.12+). Real, and it blocks anyone who starts on 3.11 before they write a
  line. Platform lane; I will pin a floor and document it.
- **`create_table.py` needs a home in `scripts/`.** Deploy is my lane; send me
  the scratchpad version or I will write it.
- **`split_case` and the founding household (your item 8).** You were right to
  raise rather than fix — and right that both backends share it. **Verified on
  main:** a case with `household_ids=['hh_a'], claim_ids=['clm_a'],
  merged_from=[]` splits to a child with **no claims** and a parent with **no
  households**. `graph/request_path.py` creates cases in exactly that shape, so
  the founding household can never be split off correctly today. That is my bug,
  in my file, reached through my code. Fixing it in `memstore` and the contract
  test; yours then follows the same rule.
- **`ruff` outside your lane (your item 7).** Known, mostly the frozen
  `core/types.py`. Not yours.

---

# Suggested order

1. **B2** — the NaN guard. Small, and it is the one that can produce a wrong
   merge rather than a missing one.
2. **C1**, **C3**, **C4** — three small ones in `scoring.py`/`store.py`, each
   with a reproduction above.
3. **C5** — the pure-function unit tests. They would have caught B2 for free.
4. **C2** and the `put_case` index key together — do the key change first and
   the concurrency fix gets simpler.
5. The rest at your pace.

B1 is not yours. Do not wait on me for the others.

Good branch. The verification discipline on it is the standard for the repo.
