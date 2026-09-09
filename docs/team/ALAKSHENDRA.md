# Alakshendra — Institutions & Remedy

> Start your Claude session with: *"Read CLAUDE.md and docs/team/ALAKSHENDRA.md
> in this repo, then help me build the jurisdiction table."*

**Your lane:** who is responsible, and what they do when you file. Yours is the
heaviest lane and it contains **the one asset that cannot be improvised on
Friday.** Start with it.

## Files you own

```
data/jurisdiction/ward12.yaml     <- Day 1. The unglamorous critical asset.
agents/remedy.py
institutions/server.py
institutions/profiles/*.yaml
eval/routing_accuracy.py
```

---

## Day 1 — the jurisdiction table

This is boring, it is manual, and it is the highest-value work in the project.
Nobody will want to do it. Do it first, before you write any agent code.

**Why it matters:** filing against the wrong body is the single most common way
a valid complaint dies, and the citizen is never told that is what happened —
only that the ticket was closed. This is documented in Bengaluru: BWSSB has
refused complaints citing BBMP's responsibility, one resident was told his issue
was resolved and *then* told his locality was out of jurisdiction, and reporting
notes that the agencies themselves "remain unsure as to which responsibility
falls under whose jurisdiction."

**Scope: one ward, water services, deep.** Roughly 30 entries. Do not do five
wards shallow — a Remedy Agent that says "I don't know" on camera is worse than
one that covers less ground confidently.

### Shape

```yaml
- service: water
  segment: ward12-4thcross
  feeder_id: bwssb-tm-14          # <- Kartik's clustering depends on this
  authority: BWSSB
  not_authority: [BBMP]           # the common wrong answer
  sla_days: 7
  statute_ref: "BWSSB Citizen Charter, supply interruption restoration"
  required_fields: [rr_number, duration_days, affected_count]
  helpline: "1915"
  ladder:
    - tier: 1
      authority: "BWSSB Section Officer"
      window_days: 7
      statute_ref: "..."
    - tier: 2
      authority: "Assistant Executive Engineer"
      window_days: 7
    - tier: 3
      authority: "Public grievance portal"
      window_days: 15
    - tier: 4
      authority: "RTI (drafted only)"
      window_days: 30
```

**`feeder_id` is the field people forget.** It costs nothing to add while you
are curating and cannot be recovered later, and Kartik's topology scoring is
useless without it. Two houses fifty metres apart on different feeders are not
the same fault.

**Real anchors to use** (these are verified, use them rather than inventing):

- BWSSB handles water supply and sewerage; BBMP handles municipal civic matters.
  The confusion between them is the failure mode, not the exception.
- BWSSB helpline **1915**. BBMP helpline **1533** (and 1533 also covers the 110
  villages absorbed into BBMP in 2008 — so the correct number depends on which
  village you are in, which is itself a great demo detail).
- **Sakala** (Karnataka Guarantee of Services to Citizens Act, 2011) gives
  statutory day counts per service, an appeal to a named Competent Officer
  quoting a GSC number, and **compensation of ₹20/day up to ₹500 deducted from
  the responsible officer's salary.** That is real teeth for tier 2+.
- Water supply / UGD connection permission: **15 working days** under Sakala.
- BBMP alone has 10,000+ pending Sakala applications; the state has over one
  lakh overdue. The system breaches its own guarantees at scale.

### Day 1 gate — do this before you go to bed

`eval/routing_accuracy.py`: assemble **50 real-ish complaints**, hand-label the
correct authority, run the table + model, measure.

**Target ≥80%.** Under that, widen the table *tonight*. Finding out on Thursday
that the headline claim doesn't hold is the worst outcome available to us.

---

## Day 2 — Remedy, then the adversary

### `agents/remedy.py`

The rule that matters: **grounded, never generative.**

```python
def resolve(claim) -> tuple[Tail, JurisdictionEntry | None, str]:
    entry = lookup(claim.service, claim.segment, claim.feeder_id)
    if entry is None:
        # SAY SO. Do not let the model guess a department.
        return (Tail.INSTITUTIONAL, None, "")
    return (Tail.INSTITUTIONAL, entry, entry.statute_ref)
```

The model's job is reading messy free text well enough to pick the right key —
service, segment, feeder. It is **not** allowed to produce an authority name.
The citation must be non-empty whenever an entry is returned.

For the five-day build every claim routes to `Tail.INSTITUTIONAL`. Still return
the tail explicitly so Ali's conditional edge is exercised and the fork is
visible in the trace.

### `institutions/server.py`

One implementation, profile-driven, five configs. Each runs as its own process:

```python
A2AServer(agent_factory=make_agent, host="0.0.0.0", port=profile.port).serve()
# agent card at /.well-known/agent-card.json
```

Ports: ward 9001, water board 9002, school 9003, vendor 9004, payments 9005.

**Each institution owns its own state and must never import `core.store`.** If
they share our table the trust boundary becomes decorative and the whole A2A
argument collapses. Give them a local dict or a small SQLite file.

### `institutions/profiles/*.yaml` — the adversary is calibrated, not moody

```yaml
name: bwssb
port: 9002
sla_days: 7
reject_malformed_rate: 0.15
unreachable_rate: 0.08
breach_rate: 0.45
false_closure_rate: 0.30
mean_response_hours: 36
calibration_note: >
  false_closure derived from reported BBMP Sahaaya behaviour -- citizens
  report tickets closed as "resolved" with no work done; one pothole
  complaint was opened and re-closed at least 15 times.
```

**Every number needs a `calibration_note` citing something real.** This is what
turns "you wrote both sides of the fight" into "we modelled the adversary from
evidence." It is also what makes the profile a *benchmark* rather than a prop —
because the rates are parameters, Kartik can sweep them.

**The false closure is the demo's peak.** Make sure the ward agent will close a
ticket as "resolved — supply restored" while claims are still live. That is what
Raghav's Watchdog disputes.

---

## Day 3-4

- Wire the escalation ladder so tier N+1 targets a different authority
- Make rejections *legible* — Ali's trace UI shows the reason string
- Help Ali test the disputed-closure path end to end
- Re-run `routing_accuracy` after the table has grown

**If you have a spare hour on Day 4:** file **one real complaint by hand**
through an actual portal, capture the genuine response, and show your simulated
agent reproducing that behaviour. One afternoon, and it converts the strawman
objection completely.

---

## Definition of done

- [ ] ~30 jurisdiction entries, every one with `feeder_id` and a non-empty `statute_ref`
- [ ] `routing_accuracy` ≥80% on 50 labelled complaints
- [ ] `remedy.resolve()` returns `None` + asks, rather than guessing, on a miss
- [ ] Five A2A servers start and serve an agent card
- [ ] No institution module imports `core.store`
- [ ] Every profile rate has a `calibration_note`
- [ ] `ruff check .` clean
