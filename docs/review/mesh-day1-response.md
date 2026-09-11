# Response — `feat/mesh-day1`

Kartik, 11 Sep, answering `docs/review/mesh-day1.md`.

Everything below was reproduced before it was touched and re-run after. The
DynamoDB numbers are against DynamoDB Local, not our table — still no
credentials on this machine, so item 4 of my Day 1 list stands.

```
pytest                                 72 passed, 23 skipped
PANCHAYAT_BACKEND=dynamodb pytest      95 passed
ruff check (this lane)                 clean
```

Both runs still carry `test_virtual_clock_compresses_a_statutory_week`, which
is pre-existing, fails on clean `f59598a` with only the stubs in place, and is
Raghav's lane. Not touched.

---

## Status of every item

| # | Item | State |
|---|---|---|
| **B1** | conftest guard breaks the contract | **Yours.** Verified unchanged, see below |
| **B2** | NaN cosine reads as perfect agreement | **Fixed**, `d16399c` |
| **C1** | byte-exact segment comparison | **Fixed**, `d16399c` |
| **C2** | read-modify-write, three writers | **Fixed**, `4c528cc` |
| **C3** | bare-string service raises on DynamoDB | **Fixed**, `aedcf0b` |
| **C4** | `RECENCY_HALFLIFE_HOURS` is not a half-life | **Fixed**, `d16399c` |
| **C5** | no test runs `store.py` | **Fixed**, `aedcf0b` — 24 + 23 tests |
| S1 | `put_case` reads on the hot path | **Fixed**, `aedcf0b` — but not the way you proposed, see below |
| S2 | `open_cases` fan-out and ordering | **Fixed**, `e751100` (ordering); fan-out argued, kept |
| S3 | member rows written by two, read by none | **Fixed**, `4c528cc` — differently, see below |
| S4 | `embed()` builds a client per call | **Fixed**, `d16399c` |
| S5 | `semantic_score` is a public trap | **Fixed**, `d16399c` — deleted |
| S6 | `_reset_is_allowed` substring-matches | **Fixed**, `aedcf0b` |
| S7 | `_iso()` is dead | **Deleted**, `aedcf0b` |
| **D2** | two new index row types | Written into the schema table |
| **D3** | TAU across the regime change | **Numbers below**, `19ecd55` |
| **D4** | `create_table.py` | In `scripts/`, at your call |

---

## B2 — the NaN cosine

You were right that this is the one that matters, and right about why: the
0.65 ceiling clustered too little and said nothing, this clustered wrongly and
said it was sure.

Guarding the inputs alone is not sufficient, which I only found by writing the
test:

```python
scoring.correlate(a_claim(embedding=[1e200, 1e200]), ...)
# 1e200 is a finite float64. Its square is not.
# norm -> inf, inf/inf -> nan, min(1.0, nan) -> 1.0, all over again.
```

So the guard is `np.isfinite` on both vectors **and** on the quotient, before
the clamp rather than after it. Four ways to have nothing to compare — absent,
empty or mismatched width, zero magnitude, not finite — all take the exit you
already built.

Your storage repro is now a test that runs on every offline `pytest`:
`test_a_value_that_overflows_float16_degrades_to_unavailable` packs `70000.0`,
gets `inf` back, and asserts `semantic_available is False`.

I left `pack_embedding` storing what it is handed. Raising there would lose the
claim, and losing the claim is worse than degrading the score — the whole
reason embedding happens in the ambient pass. Storage stores; the scorer is
what has to notice.

## B1 — confirmed still broken, still yours

Reproduced on my tip, unchanged in kind:

```bash
PANCHAYAT_BACKEND=dynamodb pytest tests/test_time_discipline.py tests/test_scoring.py
# 27 errors  (was 21; the delta is tests I added, not new breakage)
```

I have not touched `tests/conftest.py`. Your D1 remedy — skip the reset when
the backend is not local, rather than erroring — is the right shape, and the
guard in `reset()` stays where it is either way.

One thing that helps you land it: the guard now takes the endpoint as an
argument and `reset()` passes it the **live client's** endpoint, not the
environment's. Those can differ, because the table handle is built once and
cached, so a variable set afterwards moved the verdict but not the deletes.
Whatever the fixture ends up doing, the predicate is now `_reset_is_allowed(
endpoint)` and is directly callable from a fixture without touching globals.

---

## Two places I did not do what you suggested

### S1 — the feeder index key

You proposed `PK='FEEDER#<f>#SVC#<s>'`, `SK='CASE#<id>'`, on the grounds that
it is stable for the case's whole life and no orphan is possible.

**The SK was never the unstable half.** `created_at` and `case_id` are both
immutable, so `TS#<created_at>#CASE#<id>` is already stable for the case's
life. The instability is entirely in the **PK**, because `feeder_id` changes —
and dropping the timestamp out of the SK does not fix that, because the row
still moves partitions when the feeder is assigned.

What it does cost is `recurrence_count`'s `since` bound, which is a key
condition today and would become a filter — reading and billing for every case
ever opened on that feeder before discarding the old ones. That is the same
argument I made for `claims_in_window`, and I would rather not make it in
opposite directions in one file.

So the SK keeps the timestamp, and the orphan is closed two other ways:

1. **No index row is written until the case has a feeder.** The `""`-to-routed
   move is the only key change a case makes in its normal life, and there is
   now nothing at the `""` key to strand. An unrouted case is also genuinely
   not a prior case on any feeder, which is the right answer to the question.
2. **A real re-route** — a correction, not routine — is caught by
   `put_item(ReturnValues="ALL_OLD")`.

That last one also gets you the thing you actually wanted, which was the read
off the hot path. `ALL_OLD` returns the previous image **as part of the write**,
so `put_case` is one round trip, not two — `test_put_case_does_not_read_before
_it_writes` asserts zero `get_item` calls. And it removes the stale-read hazard
rather than relocating it: the old `GetItem` was an eventually-consistent read
of an item three writers touch, so it could name a feeder that was already
stale and delete the wrong row.

If you still want `CASE#<id>` after that, say so and I will take it — but I
think the cost argument survives better this way.

### S3 — the member rows

You are right that nothing read them and nothing reconciled them. I did not
delete them, for two reasons: they are a **declared entity** in the schema
table, so removing one is the same class of change as the two I asked you about
in D2; and the reconciliation objection has a fix that is better than deletion.

They now go in the **same transaction** as the case's membership update. Two
separate writes were the only way they could ever drift, so they cannot now.
`test_the_member_row_and_the_case_cannot_drift_apart` asserts the member rows
and `case.household_ids` agree after the write.

If you would rather they went away entirely, that is a schema call and I will
make it — but it should be a decision, not a cleanup.

---

## D3 — TAU across the regime change, with numbers

`eval/tau_sweep.py` was a `NotImplementedError` stub. It is the tau-sweep row
of my lane, so I filled it. **`python -m eval.tau_sweep`.**

The corpus generator models how outages happen — a main breaks, the households
on it notice over the next few hours, some at once and some the next morning —
and never reads a weight, a threshold or a score. There is a test asserting
that, because a corpus built from the scorer's own assumptions would report
that the scorer is right.

**What is measured and what is not.** The renormalised curve is measured: it is
`core/scoring.py` run over the corpus, and it is the regime every cluster in
the demo forms in. The full three-term curve is a **model** — no cosine in this
repo has ever been computed — so the semantic term is a Beta draw under a
stated assumption, exposed as `--semantic {optimistic,central,pessimistic}` so
the group argues with the assumption rather than with the conclusion. Calling
it a measurement would be the same error as showing a cluster without saying
semantic never ran.

40 incidents, 181 claims, 16290 pairs, 632 of them the same real fault. Best
threshold = lowest missed-cluster rate under a 1% false-merge ceiling:

| semantic model | `TAU_TOPOLOGICAL` | `TAU_FULL` | same-fault pairs that STOP clustering at a shared 0.72 |
|---|---|---|---|
| optimistic (same-fault cosine ~0.73) | **0.78** | 0.68 | 5 (0.8%) |
| central (~0.56) | **0.78** | 0.58 | 37 (5.9%) |
| pessimistic (semantic is noise) | **0.78** | 0.58 | 111 (17.6%) |

Three things for the group:

1. **0.72 is not the right number for either path.** The renormalised one wants
   **0.78**, in all three regimes, at zero missed clusters and under a 1%
   false-merge ceiling. That is a change we should make regardless of what
   happens to Bedrock — it is the threshold governing every cluster in the
   demo.
2. **The loss is one-way.** Across every regime, zero pairs *start* clustering
   when semantic comes on. That asymmetry is what makes a single threshold
   unsafe rather than merely suboptimal, and it is the argument for your two
   constants.
3. **I overstated the size of it on Day 1.** My item 9 said pairs that cluster
   in the demo "will stop clustering in production", which reads as a collapse.
   Under the optimistic model it is 0.8%. The real finding is the **0.20 gap
   between the two thresholds**, not the percentage — the number to defend is
   different in each regime, and that is true even where the transfer loss is
   small.

So: I back your `TAU_TOPOLOGICAL` / `TAU_FULL`, and I would add that the
topological one should move to 0.78 now rather than on the day Bedrock returns.
The trace naming which one applied matters for the same reason
`semantic_available` does.

---

## D4 — the things you took

* **`scripts/create_table.py`** — sent, and it is in this branch. That is your
  lane and I put it there because you asked for it; move, rewrite or drop it as
  you like. It is idempotent, reads the same two env vars `core/store.py`
  reads, and carries the full key table in its docstring. Verified against
  DynamoDB Local, run twice. Streams are `NEW_IMAGE` because the ambient
  Pattern Watch Lambda is triggered by a claim row arriving and needs its
  contents; GSI1 projects `ALL` because `claims_in_window` returns whole
  Claims and a `KEYS_ONLY` projection would force a GetItem per hit and undo
  the single-query cost argument.
* **`split_case` and the founding household** — waiting on your memstore fix
  and the contract test, then mine follows the same rule. My `split_case` was
  rewritten for C2 in the meantime, so the shape it lands in is:
  `_claims_of(before, hh)` is still the only source of the child's claims, and
  that is the line to change on both sides.
* **`requirements.txt` on 3.11** and **repo-wide ruff** — yours, untouched.

---

## One thing I found that is not in your review

**Segment normalisation stops at the scorer.** C1 is fixed in
`topology_score`, so `Ward12-4thCross` and `ward12-4thcross` now corroborate
correctly — *if the two claims are ever handed to the scorer together*. They
are not: `claims_in_window` queries `GSI1PK = "SEG#" + segment + "#SVC#..."`,
built from the raw string, so two casings land in **different partitions** and
Pattern Watch never retrieves the pair to score in the first place.

Same bug, one layer down, and the C1 fix cannot reach it.

I did not fix it, because the key is built from `claim.segment` on both
backends and normalising in `store.py` alone would break exactly the parity the
seam exists to enforce. It needs to be normalised once, on the way in — most
likely in intake or the Warden, before a `Claim` is ever emitted — or agreed as
a rule that both backends apply at the key.

Raising it rather than picking. It is cheap to fix now and expensive to notice
later, because the failure is silent in precisely the same way the 0.65 ceiling
was: nothing errors, the cluster just never forms.

---

B2 is not something I would have found by reading the diff either. Reproducing
every finding before writing it up is what made this review worth acting on
line by line instead of arguing with.
