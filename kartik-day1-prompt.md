# Panchayat — Day 1 prompt for Kartik (v2, current as of commit f59598a)

Paste everything below the divider into a fresh Claude session opened at the repo root.

---

Read these four files before writing any code, in this order: `CLAUDE.md`, `STATUS.md`, `docs/team/KARTIK.md`, `core/types.py`. The repo moved significantly today and `docs/team/KARTIK.md` is now the *oldest* of those — where it disagrees with `CLAUDE.md` or `STATUS.md`, the newer files win.

I am Kartik. I own the **data + mesh** lane. Today is Day 1 and I have two files to implement, in this order.

Work on branch `feat/mesh-day1`. Do not edit files outside `core/store.py` and `core/scoring.py` — with one exception noted at the bottom, which you must flag to me rather than fix silently.

## What changed since my team brief was written

Read these carefully, because my brief predates all of them:

1. **`core/store.py` is no longer imported directly by anyone.** `core/db.py` is now the storage seam. It selects a backend from `PANCHAYAT_BACKEND` — `memory` (default) or `dynamodb`. My file is the DynamoDB backend behind that seam.
2. **`core/memstore.py` already exists and is complete.** It implements the same interface in-process. **It is my reference implementation** — where behaviour is ambiguous, read memstore and match it exactly. Divergence between the two backends is the bug the seam exists to catch.
3. **`tests/test_contract.py` already exists** and is my acceptance test. The same file runs against both backends.
4. **The 0.65 ceiling has been settled** — see the "Clustering without embeddings" section of `CLAUDE.md`. Renormalise, do not zero. `CorrelationScore` has a new `semantic_available` field.
5. **Embedding does NOT happen in `put_claim()`.** `CLAUDE.md` explains why. It happens in the ambient Pattern Watch Lambda on Day 3. Storage stores.
6. **Bedrock's model data plane is blocked on our account** — every invoke returns `ValidationException: Operation not allowed`. Day 1 has no model calls, so nothing here is blocked, but it means `embed()` cannot be exercised today.

---

## Task 1 — `core/store.py` (do this first, and stop when it's done)

Implement the DynamoDB backend. Single-table design; the schema is already decided.

| Entity | PK | SK | GSI1PK | GSI1SK |
|---|---|---|---|---|
| Household | `HH#<id>` | `META` | `SEG#<segment>` | `HH#<id>` |
| Claim | `CLAIM#<id>` | `META` | `SEG#<seg>#SVC#<svc>` | `TS#<iso>` |
| Case | `CASE#<id>` | `META` | `STATUS#<s>` | `TS#<iso>` |
| Case member | `CASE#<id>` | `HH#<hh>` | — | — |
| Consent | `HH#<id>` | `CONSENT#<ts>` | — | — |
| Filing | `CASE#<id>` | `FILING#<idem>` | — | — |
| Disclosure | `HH#<id>` | `DISC#<ts>` | — | — |

The table exists: `PK`/`SK` keys, a GSI named `GSI1` on `GSI1PK`/`GSI1SK` projecting ALL, `PAY_PER_REQUEST`, streams on with `NEW_IMAGE`. `Claim.gsi1pk()` and `.gsi1sk()` exist in `core/types.py` — use them rather than rebuilding the key strings.

### How many functions

`core/db.py` declares `REQUIRED` with twelve names. **Twelve is not enough to pass the contract tests.** Verify this yourself before you start, then implement what you find:

- `test_consent_is_append_only_and_revocation_is_retroactive` calls `db.revoke_consent(...)`, which sits in `OPTIONAL`. If `store.py` omits it, `db._bind` returns the `_unavailable` stub and that test raises `NotImplementedError` under the dynamodb backend.
- `reset()` is needed for test isolation. `core/db.py` falls back to a no-op lambda when a backend lacks it, which silently produces dirty state between tests rather than an error.

So the minimum is **fourteen**: the twelve required, plus `revoke_consent` and `reset`. Full parity with memstore is seventeen — it also has `get_claim`, `open_cases`, `filings_for_case`. Implement all seventeen if time allows; they are small and the seam already declares them.

### The four that are hard to retrofit

**1. `claims_in_window()` must be a GSI1 `Query`, never a `Scan`.**

This function runs on every claim insert — it *is* Pattern Watch. If it scans, the cost argument for the whole project collapses. Query `GSI1` with `GSI1PK = "SEG#<segment>#SVC#<service>"` and a `GSI1SK` key-condition of `> "TS#<since.isoformat()>"`. Put the time bound in the **key condition**, not a `FilterExpression` — a filter reads the rows first and bills you for them. I need to show a scanned-count of zero in CloudWatch.

**2. `put_filing_once()` is a conditional put** on `attribute_not_exists(SK)`, returning `(was_written, filing)`.

Catch `ConditionalCheckFailedException`, read the **stored** filing back, and return `(False, stored)` — not the object that was passed in. `test_filing_is_idempotent` asserts exactly this by giving the retry a different `body` and checking the original comes back. Use `Filing.compute_key()` when `idempotency_key` is empty.

**3. Consent is append-only, but revocation marks rather than deletes.**

Read `memstore.append_consent` and `memstore.revoke_consent` and match their semantics. Two specifics:

- The sort key is `CONSENT#<granted_at>`, but `revoke_consent(grant_id, now)` looks up by **`grant_id`**, which is not in the key. You cannot construct the key from the argument. Query `PK = HH#<id>` with `begins_with(SK, "CONSENT#")` and filter for the matching `grant_id`, then `UpdateItem` to set `revoked_at`. Do not invent a new GSI for this.
- `revoke_consent` needs the `household_id` to build the PK but is only given `grant_id`. Read how memstore resolves this and decide the cheapest correct approach for DynamoDB. Tell me what you chose and why.
- "Append only" forbids **deleting**, not updating `revoked_at`. The test asserts the record itself survives.

**4. `Claim.embedding` must be packed before it touches DynamoDB.**

`to_dict()` passes `list[float]` straight through and boto3 refuses it — `TypeError: Float types are not supported. Use Decimal types instead.` The obvious fix is one `Decimal` per element, and that is the trap: a 1024-dim vector becomes roughly 32KB of full-precision Decimals per claim, against a 400KB item ceiling, on every write.

Pack as **base64 float16** — about 2.7KB. Convert in `put_claim`, reverse in the item→`Claim` reader, and keep the packed form entirely inside `store.py`. No other module should know it exists. Callers always see a plain `list[float]` or `None`.

`put_claim` must **never compute** an embedding — only pack one that is already present. See `CLAUDE.md`.

### `split_case()`

Reverse a merge, return the new case ids, leave the originals intact. `test_merge_then_split_restores_the_original` checks that the parent loses the household, the child gains it, and **the original claim id survives on the child**. Keep provenance in `case.merged_from`.

### Smaller notes

- `TABLE` is hardcoded to `"panchayat"`. Read `PANCHAYAT_TABLE` from the environment with that default — `app.py:46` already does exactly this.
- **Do not import `core.clock` in `store.py`.** Every function already takes `since` or `now` as a parameter. Keep the module free of ambient time.
- `tests/test_time_discipline.py` enforces that nothing calls `datetime.utcnow()`. Run it.

---

## Task 2 — `core/scoring.py`

Correlation between two claims. Pure arithmetic, no model call, ever.

```
score = 0.40*topology + 0.25*recency + 0.35*semantic
TAU = 0.72
```

Service must match exactly as a **hard gate before any arithmetic** — different service returns 0.0 immediately.

### `topology_score()`

Topology beats distance. Two houses fifty metres apart on different feeders are not the same fault; two houses four hundred metres apart on one trunk main are. Use `feeder_id`, never coordinates.

| Relationship | Score |
|---|---|
| same `feeder_id` | 1.0 |
| same `segment`, different feeder | 0.3 |
| adjacent segment | 0.15 |
| otherwise | 0.0 |

Segment ids look like `ward12-4thcross`. Implement "adjacent" simply, document the assumption in a comment, and do not invent a geo lookup.

### `recency_score()`

`exp(-delta_hours / RECENCY_HALFLIFE_HOURS)` over the absolute difference of the two `created_at` values.

### `semantic_score()` and the renormalisation rule — the important one

Cosine over `a.embedding` and `b.embedding`, brute-force NumPy. Clamp to `[0, 1]`; raw cosine goes negative and a negative component corrupts the sum.

**A missing embedding means the semantic term is unavailable, not zero.** Score it zero and the ceiling becomes `0.40 + 0.25 = 0.65`, below `TAU = 0.72` — two houses on one trunk main reporting the same fault a minute apart score a perfect 1.0 on both components that ran and still never cluster. Nothing errors; Pattern Watch simply never fires.

So drop the term and renormalise over the weights that actually ran:

```python
if a.embedding is None or b.embedding is None:
    total = (W_TOPOLOGY * topo + W_RECENCY * rec) / (W_TOPOLOGY + W_RECENCY)
    semantic_available = False
```

**Set `CorrelationScore.semantic_available` on every score you return.** While Bedrock is blocked, every cluster in the demo forms this way, and a trace that shows a cluster without saying semantic never ran is claiming agreement it did not compute.

Sanity check it against the fixture: the decoy in `fakes.the_outage()` sits on `OTHER_FEEDER`, so its topology is 0 and its renormalised ceiling is `0.25/0.65 = 0.385` — comfortably below TAU. Confirm that holds.

### `correlate()` and `embed()`

- **`correlate()` must never call `embed()`.** If either embedding is `None`, renormalise — do not fetch. A lazy Bedrock call in the scoring path puts a network round-trip on the hot path and destroys both the latency and the cost argument.
- Implement `embed()` as specified (Titan, `MODEL_EMBED`, 1024 dims) but understand it **cannot be tested today** — the account's model plane is blocked. It gets called from the Pattern Watch Lambda on Day 3.
- **No OpenSearch, faiss or pgvector.** They are a documented rejected alternative. If you want one, stop and tell me.

---

## The one thing you must flag, not silently fix

`tests/conftest.py` has an autouse `clean_store` fixture that calls `memstore.reset()` directly, regardless of which backend is active. Under `PANCHAYAT_BACKEND=dynamodb` that resets the in-memory store while the real table keeps accumulating rows between tests.

`test_recurrence_counts_only_the_same_feeder` asserts a count of exactly 3, so it will pass on a clean table and fail on the second run.

**Verify this is real before doing anything about it.** My Day-1 gate is literally "`store.py` passes `tests/test_contract.py` on DynamoDB", so if it is real, that gate cannot pass as `conftest.py` currently stands. The fix looks like one line — `db.reset()` instead of `memstore.reset()` — but `tests/` is shared and marked DONE, so: make the change on my branch, keep it as its own commit so it is trivially reviewable, and **tell me explicitly** so I can raise it in the group rather than surprising Ali in a diff.

---

## Constraints

- `core/types.py` is **frozen**. If a field looks wrong, stop and tell me — I raise it with the team, I do not edit it.
- **Nothing calls `datetime.utcnow()`.** `tests/test_time_discipline.py` enforces this. Time is passed in, or taken from `core.clock.get_clock()`.
- Dependencies are **pinned**. Do not add one without telling me.
- Storage is reached through `core.db`, never by importing `core.store` directly — that applies to any test or helper you write too.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  ```

## Acceptance — my Day 1 gate

```bash
pytest                                  # memory backend, no AWS, must stay green
PANCHAYAT_BACKEND=dynamodb pytest       # the real table — this is the gate
ruff check .
```

Both backends must pass the *same* tests. If memory passes and DynamoDB fails, DynamoDB is wrong.

Tell me explicitly which of these you have verified rather than assumed:

- [ ] All fourteen (or seventeen) functions implemented; `core.db` imports clean under `PANCHAYAT_BACKEND=dynamodb`
- [ ] `claims_in_window` is a Query with the time bound in the key condition, not a filter
- [ ] `put_filing_once` returns `(False, stored)` with the *stored* body on retry
- [ ] `split_case` leaves the parent intact and the child carrying the original claim id
- [ ] `revoke_consent` marks rather than deletes, and `live_consents` respects it
- [ ] Embeddings round-trip through base64 float16; `put_claim` never computes one
- [ ] `correlate()` renormalises when an embedding is missing and sets `semantic_available=False`
- [ ] The decoy in `fakes.the_outage()` does not cluster
- [ ] `scoring.py` imports no model client and `correlate()` never calls `embed()`
- [ ] `ruff check .` clean

## How I want you to work

Show me the plan before writing code. Do `store.py` first and **stop when it passes the contract tests on both backends** — three teammates are unblocked by the seam already, but the DynamoDB gate is mine and I want it green before `scoring.py` starts.

If any instruction here conflicts with `CLAUDE.md`, `STATUS.md`, or what you find in `memstore.py`, say so rather than picking one silently. `memstore.py` is the behavioural reference; this prompt is not.
