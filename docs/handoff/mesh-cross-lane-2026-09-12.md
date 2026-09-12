# Open items that are not one lane's to close — mesh lane, 12 Sep

Kartik. Everything below was **reproduced by executing it** against `main` at
`96215ae` plus `feat/mesh-day3`, not inferred from reading. Each item says what
it is, how to see it, why it matters, and whose it is.

Nothing here is a complaint about anyone's code. These are all seams — the
places where two lanes meet and neither side is wrong on its own.

---

## Ranked by what breaks if it is still open on Friday

| # | Item | Blocks | Owner |
|---|---|---|---|
| **1** | Nothing can resolve a case | **the density curve — the number the project stands on** | Raghav + Alakshendra |
| **2** | Nothing captures consent to join a collective | every collective filing, legally | Raghav + Ali |
| **3** | `split_case` loses the founding household | hard rule 6, reversibility | Ali |
| **4** | `climb()` submits without reading the signature | hard rule 4 | Raghav |
| **5** | `escalation_tier` has two writers, no mechanism | escalation correctness | Raghav + me + group |
| **6** | No case-merge primitive | hard rule 5, duplicate filings | Ali + Raghav |
| **7** | Segment normalisation stops at the scorer | clustering, silently | Raghav or a group rule |
| **8** | `memstore.recurrence_count` diverges from DynamoDB | backend parity | Ali |
| **9** | GSI1 is keyed on segment, clustering is by feeder | clustering completeness | Ali |
| **10** | TAU across the regime change, unratified | the merge policy | group |

---

## 1. Nothing in the repo can resolve a case

**BLOCKS THE DENSITY CURVE, WHICH IS DUE TOMORROW.**

```bash
grep -rn "CaseStatus.RESOLVED" --include=*.py agents/ graph/ institutions/
# nothing. RESOLVED appears once in the whole repo, in its own enum definition.
```

Statuses actually written anywhere: `BREACHED`, `DORMANT`, `DRAFTED`,
`TRACKING`.

**Why it is the worst one.** `eval/density_curve.py` plots resolution rate
(y) against corroborated household count (x). It is the project's thesis made
falsifiable: *every household reports alone; the street gets the leverage.* If
the rate climbs with N, collective pressure demonstrably works. That is why the
brief calls it "the number the project stands on".

With no resolution to measure the curve comes out **flat at zero for every N**
— and a flat-at-zero curve is visually indistinguishable from the real negative
result. There is a large difference between:

* *"the curve is flat"* — a genuine finding, worth reporting honestly
* *"the curve cannot be drawn"* — a missing instrument

Today it is the second and it would read as the first. The brief says if the
curve is flat, tell the group Thursday rather than Friday — and that assumes
the instrument works. Reframing the project around a measurement artefact is
the worst available Thursday.

**Where the chain stops:**

```
household reports -> claim                     works
claim -> case                                  works
Pattern Watch merges -> corroboration          works        <- the x-axis
case -> filing -> desk                         submit defaults to lambda: True
desk replies CLOSED                            the simulator produces it
something polls the desk for that reply        nothing calls client.status()
reconcile_closure decides disputed or not      exists, returns a bool
  not disputed -> case.status = RESOLVED       NOTHING WRITES IT
```

Three holes, all at the far end:

1. `agents/watchdog.py:94` — `self._submit = submit or (lambda filing: True)`.
   Not wired to a desk; every filing "succeeds" unconditionally.
2. `InstitutionClient.status()` exists and has **zero callers** outside tests.
3. `reconcile_closure()` returns a bool and writes no status. The verdict goes
   nowhere.

**The good news, and why this is worth building rather than stubbing.**
`institutions/profiles/bwssb.yaml` sets `false_closure_rate: 0.30` — thirty
percent of CLOSED replies are the institution lying, calibrated against the
documented Sahaaya/BBMP behaviour in CLAUDE.md's opening paragraph. So the
honest y-axis is not "did the desk close it" but **"closed, and survived the
dispute check"**, which is a far better number and is the demo's peak moment.
Alakshendra's profile comment says so outright: *"every rate below is a
parameter, so Kartik can sweep it and the resolution-rate number means
something. That is the difference between a benchmark and a prop."*

**Smallest thing that unblocks me:** piece 3 alone. `reconcile_closure` already
decides; something has to write `RESOLVED` on the not-disputed branch. Pieces 1
and 2 turn it from a simulation into a measurement.

---

## 2. Nothing captures consent to join a collective

```python
# ConsentScope.JOIN_COLLECTIVE -- "merge me into a group case", frozen since day one
grep -rn "JOIN_COLLECTIVE" --include=*.py agents/ graph/ core/
# only core/types.py (the definition) and agents/anti_abuse.py (my new check)
```

`agents/pattern_watch.apply_upgrade()` is **the first code path in the repo
that performs the action this scope exists to authorise**, and until yesterday
it merged households into a collective filing against a public body without
checking. `anti_abuse.verify()` now refuses a claim that does not carry it.

**That refuses most traffic today, and that is the honest state rather than a
bug in the check:**

* `core/fakes.py` grants `FILE_INDIVIDUAL` and nothing else
* `graph/request_path.py:234` emits `consent_scopes=[]` while the Warden is stubbed
* no intake step anywhere asks the household the question

**Whose.** Raghav owns `agents/warden.py` and `agents/intake.py`, so the
capture is his lane; Ali owns the graph that would surface the ask.
`AntiAbuse(require_join_consent=False)` exists so the group can stand it down
*deliberately* — but the default stays strict, because a filing made in a
household's name is exactly what hard rule 4 is about, and hard rule 7 says
aggregation points outward only.

---

## 3. `split_case` still loses the founding household

Ali took this as D4 on 10 Sep ("Fixing it in `memstore` and the contract test;
yours then follows the same rule"). **Still reproduces on `main` today:**

```python
case = fakes.a_case(claim_ids=['clm_a'], household_ids=['hh_a'], merged_from=[])
db.put_case(case)
kids = db.split_case(case.case_id, ['hh_a'])

db.get_case(kids[0]).claim_ids    # []   <- child has no claims
db.get_case(case.case_id).household_ids  # []   <- parent has no households
```

A case's founding household is in `household_ids` but never in `merged_from`,
and `_claims_of` reads only `merged_from`. `graph/request_path.py:395` creates
cases in exactly that shape, so **the founding household can never be split off
correctly**. Hard rule 6 says merges are reversible; this one is not.

Flagging only because it was taken and is still open — I have deliberately not
touched it, since fixing one side of the seam breaks the parity it exists to
enforce.

---

## 4. `climb()` submits without ever reading a signature

This one has **moved** since it was last raised, and half of it is now closed.

`agents/digest.py` can record a signature — `signature_requests()` builds the
queue and `sign_filing()` writes it (and as of yesterday that works on the
DynamoDB backend too, which it did not before). So the capture exists.

What is still open: `agents/watchdog.py::climb()` never sets or consults
`Filing.signed_by` for any tier, and its own comment at line 232 says so. Once
`submit` is wired to `institutions/client.py`, `file()` returns `NEEDS_HUMAN`
for an unsigned filing — correctly — so **every tier would fail NEEDS_HUMAN
forever** until `climb()` reads what the digest captured.

Ali has already answered the policy question: *every tier needs a fresh
signature* — tier 1 is a complaint, tier 3 is a statutory appeal that can dock
an officer's pay under Sakala, tier 4 needs a name, address and Rs 10.

**Whose:** Raghav, and it is now a wiring job rather than a design one.

---

## 5. `escalation_tier` has two writers and no agreed mechanism

My `apply_upgrade()` and Raghav's `climb()` both want to raise it, and
`put_case` is a blind whole-item overwrite. Lost update or double escalation
— filing at the wrong tier against the wrong authority — are both live.

**What I did rather than decide it alone:** `apply_upgrade` does not write the
tier. It emits `tag=pattern event=escalation_requested` and leaves the write to
whichever mechanism the group picks. That is the first of the two options the
blocker itself names (`climb()` as sole writer, `apply_upgrade` requesting).
Pinned by a test so nobody "fixes" it by accident.

Ali's handoff asks for **one conditional-write design agreed once**, because
three people inventing three mechanisms is the failure mode. Still unratified.

**Related and measured:** my Day 1 fix narrowed the membership writes but
`put_case` remains a full overwrite, so the hazard runs in one direction still.
Measured on DynamoDB Local:

```
watchdog reads case -> ambient adds hh_new -> watchdog writes whole item
  escalation_tier : 2    (the watchdog's write landed)
  household_ids   : []   (the household that joined is GONE)
```

That is mine to fix once the mechanism is agreed.

---

## 6. No case-merge primitive

`graph/request_path.py:501` — `case_id = payload.get("case_id") or new_id("case")`.
Every report mints a new case, so twelve households reporting one outage open
twelve `DRAFTED` cases on one feeder.

Pattern Watch merges *claims* into one case. Doing that naively would leave the
other eleven alive, each with its own deadline and tier, for the Watchdog to
file separately against BWSSB for the same fault — hard rule 5's duplicate that
"reads as spam and gets both copies closed", with provenance `split_case`
cannot reconcile.

**What I did:** claims already live on another open case are **skipped**, and
the skip is traced (`tag=pattern event=claims_on_other_cases`). Safe, and it
means clustering does less than it should.

**The real answer is one of two**, and both are outside my lane: a case-merge
primitive that withdraws the others with provenance, or the spine reusing a
case per feeder+service instead of minting per report. **Ali + Raghav.**

---

## 7. Segment normalisation stops at the scorer

`core/scoring.topology_score` normalises case and whitespace, so
`Ward12-4thCross` and `ward12-4thcross` corroborate correctly — *if the two
claims are ever handed to the scorer together*. They are not:

```python
db.put_claim(a)  # segment='ward12-4thcross'
db.put_claim(b)  # segment='Ward12-4thCross'
db.claims_in_window('ward12-4thcross', WATER, since)  # -> 1 claim
db.claims_in_window('Ward12-4thCross', WATER, since)  # -> 1 claim
```

`GSI1PK` is built from the raw `claim.segment`, so two casings land in
different partitions and Pattern Watch never retrieves the pair to score in the
first place. Same bug one layer down, and the scorer's fix cannot reach it.

Not fixed in `store.py` alone because the key is built from `claim.segment` on
both backends and normalising one side breaks the parity the seam enforces. It
needs normalising **on the way in** — intake or the Warden, before a `Claim` is
emitted — or agreeing as a rule both backends apply at the key. **Raghav, or a
group rule.**

Silent in exactly the way the 0.65 ceiling was: nothing errors, the cluster
just never forms.

---

## 8. `memstore.recurrence_count` diverges from the DynamoDB backend

After a split, the two backends disagree:

```
memory   : one incident, two households -> 1     after one split -> 2
dynamodb : one incident, two households -> 1     after one split -> 1
```

I stopped the DynamoDB side ratcheting (merge/split/merge/split climbed
1→2→3→4 for one incident, on the number the escalation argument rests on) by
not filing a feeder index row for a split child, which carries
`split_from:<parent>` in `merged_from`. memstore counts `Case` objects and so
still counts the child.

One condition in a comprehension:

```python
and not any(t.startswith("split_from:") for t in c.merged_from)
```

`core/memstore.py` is shared, so raised rather than edited. **Ali.**

---

## 9. GSI1 is keyed on segment; clustering is by feeder

The design's own example is two houses 400m apart on one trunk main — a
different street. `claims_in_window` is keyed `SEG#<segment>#SVC#<service>`, so
a single query retrieves half of exactly the fault the system exists to notice.

`pattern_watch` works around it by fanning out over the segments of cases
already in flight on that feeder — bounded by open cases on one main, still on
the index, never a scan. A feeder-keyed GSI answers it in **one** query.

Schema change, so raised rather than taken. **Ali.**

---

## 10. TAU across the regime change — still unratified

Ali's position (two thresholds, `TAU_TOPOLOGICAL` and `TAU_FULL`, swept
independently, trace naming which applied) matches mine. It has never been
ratified, and `core/scoring.TAU` is still one number at 0.72.

**Numbers refreshed today** on the new corpus — one that contains silent
households, which the previous one did not:

| semantic model | `TAU_TOPOLOGICAL` | `TAU_FULL` | same-fault pairs that stop clustering at a shared 0.72 |
|---|---|---|---|
| optimistic | **0.82** | 0.70 | 0.4% |
| central | **0.82** | 0.64 | 4.0% |
| pessimistic | **0.82** | 0.60 | 17.4% |

`python -m eval.tau_sweep --semantic {optimistic,central,pessimistic}`.

Two things the group should note. **0.72 is not the right number for either
path** — the renormalised one wants 0.82 in all three regimes, at zero missed
clusters under a 1% false-merge ceiling, and that is worth changing regardless
of what happens to Bedrock. And **the loss is one-way**: across every regime,
zero pairs ever *start* clustering when semantic comes on. That asymmetry is
what makes a single threshold unsafe rather than merely suboptimal.

---

## Smaller, still not mine

* **`requirements.txt` has no Python floor.** `numpy>=2.5.3` needs 3.12+, and
  nothing in the file or `pyproject.toml` says so. Anyone starting on 3.11 is
  blocked before they write a line. Ali.
* **`core/tags.py` ownership.** Still says *"proposed by Alakshendra for the
  institutions lane. Shared — Ali, if the trace UI wants a different shape, say
  so and this moves."* Three lanes emit into it now. Ali said he would take it
  into platform; not yet moved.
* **`MergeProposal` has no field for "this check could not run".** I am riding
  it in the emitted trace (`checks_not_run=`) rather than overloading
  `rejection_reasons`, which is typed claim_id → reason. If the trace UI wants
  it on the proposal it is a `core/types.py` change and therefore all four of
  us. Ali.

---

## What I am asking for, concretely

**Before tomorrow's morning gate:** item 1, piece 3. One branch, one write —
`reconcile_closure` says not-disputed, something sets `RESOLVED`. Without it I
cannot produce the density curve at all, and "cannot draw it" will look exactly
like "the thesis is wrong".

**Before Friday:** items 2 and 4, because between them they decide whether a
collective filing can lawfully and mechanically happen at all.

**Whenever the group next sits down:** items 5 and 10. Both are one decision
each and both have a written proposal already.
