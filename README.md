# Panchayat

**Every household reports alone. The street gets the leverage.**

A neighbourhood agent mesh built with the [Strands Agents SDK](https://strandsagents.com)
and deployed on Amazon Bedrock AgentCore. Entered in the **Good Neighbor** track
of the AWS *Agents for Humans* hackathon.

---

## The problem

When the water fails on a Tuesday, the building WhatsApp group knows within
fifteen minutes. Discovery was never the problem.

What nobody has is the **stamina** — to file against the right body first time,
track a statutory clock across eleven weeks, notice the day it breaches, climb
to the next authority, and remember that this is the fourth failure on this
trunk main since June.

That gap is documented rather than imagined. Bengaluru citizens report civic
tickets closed as *"resolved"* with no work done; one pothole complaint was
opened and re-closed at least fifteen times by hand. The agencies themselves
"remain unsure as to which responsibility falls under whose jurisdiction," which
is why filing against the wrong body is the most common way a valid complaint
quietly dies.

**Panchayat does not fix pipes.** It pursues resolution, relentlessly, and asks
a human exactly one question when there is a real decision to make.

## How it works

A spine, a membrane, and an ambient layer.

- **The spine** runs for one household with one problem, start to finish, with no
  neighbours involved. `SIGNAL → DELIBERATE → REPRESENT → ACT → TRACK →
  ESCALATE → CLOSE`
- **The membrane** is the Privacy Warden. Nothing reaches the outside except
  through it, and what crosses is a *claim* — never identity, income, health or
  schooling.
- **The ambient layer** watches the claim stream and **upgrades a case already in
  flight** when a pattern crosses threshold. Nobody opts into collective action;
  it happens to them, and then they are told.

Eight agents across four execution paths, using four of the Strands multi-agent
patterns — Swarm inside a household, Graph for the request path, Agents-as-Tools
for grounded lookups, and A2A at every trust boundary. Five more agents stand on
the far side of that boundary as institution desks, in their own processes with
their own state.

The escalation ladder is deliberately **not** a Strands `Workflow`. It is driven
by the Watchdog across weeks, on wakes from EventBridge — and no Workflow
invocation survives a seven-day statutory window, for the same reason the
ambient and temporal paths are not Graph nodes.

> We use A2A not because it is impressive, but because a Swarm shares a mutable
> context across every agent in it — and that is precisely what we promised never
> to do across households.

## Repo

```
core/        contracts, clock, store, scoring     <- types.py is frozen
agents/      the eight
graph/       the request path
institutions/ A2A servers, calibrated profiles
data/        curated jurisdiction, synthetic corpus
eval/        routing accuracy, tau sweep, density curve
docs/team/   one brief per person
```

## Getting started

Read **`CLAUDE.md`** first — it is the shared context and it has the rules that
are expensive to get wrong. Then **`docs/SETUP.md`**, then your own brief in
`docs/team/`.

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env
python -c "from core.types import Claim; from core.clock import get_clock; print('ok', get_clock().now())"
```

## What we deliberately do not do

- **No autonomous police filing.** Read, track and advise only.
- **Agents draft, humans sign.** Nothing is submitted to a public body without a
  named person approving it — a wrongly filed complaint creates liability for
  that household, not for us.
- **Aggregation points outward only.** Collective pressure may be assembled
  against an institution, never against a person or a household.
- **Minimisation, not anonymity.** Eight houses on a cross street means any claim
  precise enough to file is precise enough to identify. We do not pretend
  otherwise. We guarantee that income, health, arrears and schooling never cross
  the membrane.

## Team

| Who | Lane | GitHub |
|---|---|---|
| Ali | platform + lead | [@LycanAlan](https://github.com/LycanAlan) |
| Kartik | data + mesh | [@ShipWithKartik](https://github.com/ShipWithKartik) |
| Alakshendra | institutions | [@AlakshendraB](https://github.com/AlakshendraB) |
| Raghav | household + time | [@Raghav](https://github.com/Ragh234) |

One brief per person in `docs/team/`.
