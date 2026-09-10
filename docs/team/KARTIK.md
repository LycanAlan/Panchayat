# Kartik — Data & Mesh

> Start your Claude session with: *"Read CLAUDE.md and docs/team/KARTIK.md in this
> repo, then help me build core/store.py."*

**Your lane:** everything the mesh knows and how it notices patterns. You own
the table, so **three people are blocked on you for the first two hours.**

## Files you own

```
core/store.py            <- Day 1 morning. Everyone waits on this.
core/scoring.py
agents/pattern_watch.py
agents/anti_abuse.py
data/corpus/generator.py
eval/tau_sweep.py
eval/density_curve.py
```

Do not edit files outside this list. If you need something from another lane,
use the signature already in their stub.

---

## Day 1 — unblock everyone, then score

### First: `core/store.py` (target: done by lunch)

Ali creates the table; you write the only module that talks to it. The schema
is already decided — implement it, don't redesign it:

| Entity | PK | SK | GSI1PK | GSI1SK |
|---|---|---|---|---|
| Household | `HH#<id>` | `META` | `SEG#<segment>` | `HH#<id>` |
| Claim | `CLAIM#<id>` | `META` | `SEG#<seg>#SVC#<svc>` | `TS#<iso>` |
| Case | `CASE#<id>` | `META` | `STATUS#<s>` | `TS#<iso>` |
| Case member | `CASE#<id>` | `HH#<hh>` | — | — |
| Consent | `HH#<id>` | `CONSENT#<ts>#<grant_id>` | — | — |
| Filing | `CASE#<id>` | `FILING#<idem>` | — | — |
| Disclosure | `HH#<id>` | `DISC#<ts>#<uniq>` | — | — |
| **Case by feeder** | `FEEDER#<f>#SVC#<svc>` | `TS#<iso>#CASE#<id>` | — | — |
| **Grant pointer** | `GRANT#<grant_id>` | `META` | — | — |

The last four rows differ from the table as it was handed to me. All four were
raised on Day 1 and **approved by Ali in `docs/review/mesh-day1.md`, D2**. None
adds a GSI and none changes a declared entity key.

* **Case by feeder.** `recurrence_count()` asks "how many prior cases on this
  feeder", and the declared Case GSI1 is keyed on `STATUS#`, so there is no
  index on `feeder_id` at all. Without this row that question is a Scan with a
  filter — on the number most of the escalation argument rests on. The SK
  carries `created_at` so the `since` bound is a key condition rather than a
  filter over every case the feeder ever had. A row is written only once the
  case HAS a feeder, which is what stops the `""`-to-routed transition
  stranding one: a stale row would be a permanent +1, drifting in the direction
  that manufactures a pattern.
* **Grant pointer.** `revoke_consent()` is handed a `grant_id` and needs the
  `household_id` to build the PK. The alternatives were a Scan with a filter
  (which in a single-table design reads every claim, case and filing to find
  one consent row) or a second GSI. One small write on a rare path makes
  revocation two O(1) calls, and it lands in the same transaction as the
  consent so the two cannot drift.
* **The two uniquifiers.** `CONSENT#<ts>` alone collides when a household
  grants two scopes in one tick — one screen, two checkboxes — and the second
  silently overwrites the first. `DISC#<ts>` collides the same way when two
  fields are released together, and there it under-reports the cumulative
  disclosure budget, in the direction that lets more through. memstore keeps
  both rows in each case. An append-only log that silently drops a row is the
  one bug this table must not have.

`Claim.gsi1pk()` and `.gsi1sk()` already exist in `core/types.py`. Use them.

**Three things to get right, because they are hard to retrofit:**

1. **`claims_in_window()` is a GSI1 query, never a scan.** This one function is
   Pattern Watch. If it scans, the whole cost argument collapses.
2. **`append_consent()` never updates in place.** Sort key is the timestamp, so
   history accumulates. Raghav's scope-drift check reads it, and the whole
   point is proving what a household agreed to eleven weeks ago.
3. **`put_filing_once()` is a conditional put** on `attribute_not_exists(SK)`.
   Returns `(was_written, filing)`. When it returns `False`, hand back the
   *stored* filing — a retrying Watchdog must not file twice.

### Then: `core/scoring.py`

```
score = 0.40*topology + 0.25*recency + 0.35*semantic
service must match exactly (hard gate, before any arithmetic)
```

**Topology beats distance, and this is the subtle one.** Two houses fifty metres
apart on different feeders are not the same fault. Two houses four hundred
metres apart on one trunk main are. Use `feeder_id`, not coordinates:

| Relationship | Score |
|---|---|
| same `feeder_id` | 1.0 |
| same segment, different feeder | 0.3 |
| adjacent segment | 0.15 |
| otherwise | 0.0 |

`recency = exp(-delta_hours / 48)`.

`semantic` = cosine over Titan embeddings, **brute-force NumPy**. A neighbourhood
has hundreds of claims, not millions — cosine over 500 vectors is microseconds.
**Do not provision OpenSearch.** It is a day of setup, a slice of the credits,
and slower end to end at this cardinality. If you find yourself reaching for a
vector database, that is the signal to stop and message the group.

Store embeddings as a base64 float16 attribute on the claim item (~3KB, well
inside the 400KB item limit).

**No LLM in `scoring.py`. Ever.** If a model call appears in that file, the
cost argument and the latency argument both die.

---

## Day 2 — corpus, and the sanity check

### `data/corpus/generator.py`

**Critical: this file must not import `core.scoring`.** Write the failure model
first — pick a feeder, decide it fails, decide which households notice, decide
which of those bother to report — *then* emit claims. If the generator knows
about the scorer, the density curve measures itself and the number is worthless.

Model a realistic reporting rate. Not everyone on a failed main complains;
somewhere around 25-40% is honest.

### The 90-minute sanity check

Run the scorer over the corpus and **eyeball whether the clusters it forms are
the ones you would have drawn by hand.** That is the whole test. If they match,
move on — this is a check, not a gate. We already established the correlation is
plumbing rather than a hypothesis: a trunk main serves many houses and fails for
all of them at once.

---

## Day 3 — the thesis

### `agents/pattern_watch.py`

Triggered by **DynamoDB Streams**, filtered to `CLAIM#` inserts. Not by a case,
not on a timer.

```
on_new_claim -> score against open claims (arithmetic, no model)
             -> below TAU: stop. no model invoked, nothing logged as interesting.
             -> above TAU: adjudicate() -- the one LLM call in your lane
             -> anti_abuse.verify() gates it
             -> apply_upgrade() mutates a case already in flight
```

`apply_upgrade` must: merge filings, raise corroboration, recompute
`recurrence_count`, raise the escalation tier, and **keep provenance in
`case.merged_from` so `split_case()` can undo it.** A false merge is worse than
no merge — a bogus collective filing gets dismissed and takes nine valid
individual complaints with it.

### `agents/anti_abuse.py`

Checks in order, and each one has to actually reject something in the demo:

1. distinct registered households — two member agents in one household is *one*
2. address verified against the RWA flat register
3. `feeder_id` actually matches — different trunk main, reject
4. corroborate against a public outage feed where one exists

Populate `rejection_reasons` with readable strings. Ali's trace UI renders them
and they are what makes this agent visibly do work rather than nod.

---

## Day 4 — the number

`eval/tau_sweep.py` — sweep TAU, plot false-merge rate against missed-cluster
rate, pick the knee with evidence. Do not defend a hardcoded number.

`eval/density_curve.py` — run at **N = 1, 5, 10, 20** against a fixed institution
profile. State precisely what it measures: *resolution rate against corroborated
household count for a calibrated institution.* That is the system being
measured, not your generator.

**This is the number the project stands on.** If the curve is flat, tell the
group on Thursday, not Friday — we have a day to reframe honestly.

---

## Definition of done

- [ ] `claims_in_window` is a Query, verified in CloudWatch (zero scanned count)
- [ ] `put_filing_once` returns `(False, stored)` on the second call
- [ ] `split_case` restores originals intact
- [ ] `scoring.py` imports no LLM client
- [ ] `generator.py` does not import `core.scoring`
- [ ] pytest coverage for scoring that runs with no AWS credentials
- [ ] `ruff check .` clean
