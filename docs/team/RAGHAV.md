# Raghav — Household & Time

> Start your Claude session with: *"Read CLAUDE.md and docs/team/RAGHAV.md in
> this repo, then help me finish core/clock.py."*

**Your lane:** everything left of the membrane, plus time itself. You own the
two agents that carry the demo's best moments — the Warden refusing to leak, and
the Watchdog refusing a closure.

## Files you own

```
core/clock.py            <- Day 1. Already drafted; finish and test it.
agents/intake.py
agents/household.py
agents/warden.py
agents/watchdog.py
video/                   <- the demo video (yours since 14 Sep)
```

---

## Day 1 — the clock

`core/clock.py` is already written. Your job is to make it real, test it, and
guard the rule that makes it honest:

> **Both implementations call the same Watchdog function.**

Seven statutory days cannot elapse inside a five-day build, so `VirtualClock`
runs at `TIME_SCALE=86400` — one statutory day per real second. But if the demo
path and the production path diverge, the compressed demo becomes exactly the
"simulated away the hard part" failure a judge will smell.

**Never write `if demo_mode:` inside the Watchdog.** If you want to, the clock
abstraction is wrong and you should fix the clock instead.

One correction worth knowing, because an earlier version of our plan had it
wrong: **AgentCore Runtime's eight-hour session is not a scheduler.** It is a
session ceiling. Statutory windows are days. So the Watchdog is stateless
between wakes and every bit of case state lives in Kartik's DynamoDB.

Write `tests/test_clock.py` first: schedule something seven virtual days out at
`TIME_SCALE=86400`, assert the callback fires in roughly seven real seconds.
That test is your proof for the video.

Also: **nothing in the repo calls `datetime.utcnow()`.** Grep for it on Day 4
and fix anything you find, including in other people's files.

---

## Day 2 — intake and the household

### `agents/intake.py`

Text in (voice is out of scope — do not start a Twilio trial). Two jobs:

1. **One sentence often contains more than one problem.** *"Three days now, no
   water in the tank, and I have to send Divya to school tomorrow"* is a supply
   failure **and** a transport need. Return one dict per need.
2. **Read back before acting.** Bad transcription pursued for eleven weeks is
   failure mode #1. Cheap to build, and it shows well on camera.

### `agents/household.py`

A Strands `Swarm` across member agents:

```python
Swarm([parent, teen, elder], entry_point=parent, max_handoffs=6,
      max_iterations=8, execution_timeout=90.0, node_timeout=30.0)
```

`Swarm` maintains a mutable `SharedContext` every agent reads and writes. That
is **correct inside one household** and catastrophic across households — which
is the verified reason the mesh uses A2A instead of a bigger swarm. Know that
sentence; it goes in the video.

**Only run the swarm when a problem touches more than one member.** A wrong
electricity bill needs no family debate, and burning a swarm on it is waste.

**The thing that makes this layer justify itself:** the position it returns can
contain facts the reporter never mentioned. In our walkthrough the parent says
nothing about dialysis, and the household position comes back carrying a hard
06:00 deadline pulled from the grandmother's context. Build a fixture that
demonstrates exactly that — it is one of the three best moments we have.

Return `HouseholdPosition`. **Never** return a `Claim`. Only the Warden makes
those.

---

## Day 3 — the Warden, in this order

### First: `minimise()` — field minimisation

This is most of the value and it must work.

```
budget_ceiling_inr=500        -> has_budget_ceiling=True
deadline_reason="dialysis"    -> priority=HIGH, reason_withheld=True
```

We do **not** promise anonymity, and do not let anyone write that we do. Eight
houses on a cross street means any claim precise enough to file is precise
enough to identify — geographic granularity *is* identity in a neighbourhood.
What we guarantee is that income, health, arrears and schooling never cross.

### Second: `check_inference_leak()` — cuttable if Friday goes wrong

A household that declines Tuesday and Friday swaps has told the mesh someone has
a Tuesday-Friday commitment. **The leak is in the correlation, not the field**,
so no schema catches it. This is the most original thing in the project — build
it if the first two land, cut it before you cut anything of Kartik's.

### Third: `consent_covers()` — scope drift

A blanket grant given three weeks ago for a *garbage* complaint does not cover a
water case. Re-ask rather than assume. Reads Kartik's `live_consents()`.

**The argument to remember:** a component that both holds the secrets and decides
disclosure cannot audit itself. That is separation of duties, not a flourish —
it is why the Warden is its own agent and not a prompt instruction inside the
Household Agent.

---

## Day 3-4 — the Watchdog

```
watchdog(case_id, action)     # one entry point, both clocks
  reconcile_closure(case_id)  # THE moment
  climb(case_id, clock)       # ordered tiers, statutory deadlines
```

### `reconcile_closure()` is the peak of the whole demo

The institution says *resolved — supply restored*. Seven households' live claims
say otherwise. **The Watchdog disputes the closure using ground truth the
institution does not have** — and which a citizen could never have either,
because you know your own tap, not your neighbours'.

This is the single thing in the system a person genuinely could not do for
themselves. Give it a clean log line; it goes on screen in your video.

### `climb()`

Ordered tasks with real deadlines, from Alakshendra's ladder. Tier 4 drafts an
RTI which needs a citizen's name, address and ₹10 fee — **and the system supplies
none of the three.** Draft only. This is a hard guardrail, not a limitation to
apologise for.

Other behaviours the failure-mode table promises:

- institution unreachable → **pause the SLA clock**, don't run it against a
  filing that never landed. Retry twice, then surface.
- draft unsigned after 7 days → expire it, one notice, case goes dormant
- household withdraws → honoured retroactively, count drops, filing amended

---

## Definition of done

- [ ] `test_clock.py` proves 7 virtual days fire in ~7 real seconds
- [ ] Zero `datetime.utcnow()` outside `core/clock.py` (grep the whole repo)
- [ ] No `if demo_mode:` anywhere in `agents/watchdog.py`
- [ ] A fixture where the household position carries a fact the reporter never said
- [ ] `minimise()` provably drops budget and health fields — test it adversarially
- [ ] `reconcile_closure` disputes a false closure using other households' claims
- [ ] `ruff check .` clean

---

## The video

Yours since 14 Sep. The project, its script and the render steps live in
`video/` (see `video/README.md`). This guidance moved here from Ali's brief.

Three moments, in this order:

1. **Grounded routing**, citation visible — establishes it is looked up, not guessed
2. **The upgrade** — the case mutating without anyone requesting it
3. **The disputed closure** — the peak; give it room

**One line of setup so a non-Indian judge knows false closure is normal**, not
scandalous. Without it, our best moment reads as confusing rather than damning.

Say out loud, because both are answered in the docs and absent from most videos:

- *"For one household chasing its own problem, one agent would do. The mesh
  earns itself where two households' interests meet without merging their data."*
- *"We used A2A not because it's impressive, but because a Swarm shares a mutable
  context across every agent in it — and that's precisely what we promised never
  to do across households."*

Close on the two numbers: the density curve, and *eleven weeks, nobody spent
more than four minutes.*

**Open the repo before you record.** A great video over thin code is worse than
a plain video over solid code — judges who look afterwards feel sold to.
