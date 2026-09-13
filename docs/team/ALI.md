# Ali — Platform, Integration & Lead

**Your lane:** the wiring, the deploy, the evidence, and the story. You also
unblock three people, which on a five-day clock is most of the job.

## Files you own

```
app.py
graph/request_path.py
agents/digest.py
demo/trace_ui/
docs/          (submission copy)
infra/         (table, lambda, scheduler, roles)
```

---

## Before anyone else can start

Work `docs/SETUP.md` Part 1 top to bottom. In priority order, because each one
blocks somebody:

1. **Request the $50 credits now.** Approval is not instant. Do this first, today.
2. **Bedrock model access** — Nova Lite, Haiku 4.5, Sonnet, and **Titan Text
   Embeddings V2**. Kartik cannot write `scoring.py` without Titan.
3. **Confirm the exact inference-profile IDs in the console** and paste them
   into the group. They carry a region prefix like `us.anthropic.…`, and a wrong
   ID is a twenty-minute detour someone takes at the worst moment. Do not trust
   the IDs in `.env.example`, including ours.
4. **Create the DynamoDB table with GSI1 and streams on** — Kartik is blocked.
5. **Four IAM users, keys sent privately.** Not the group chat, not a screenshot.
6. **Push this repo, add three collaborators, protect `main`.**

Install AWS CLI first — it is not on your machine:
`winget install -e --id Amazon.AWSCLI`, then reopen the terminal.

---

## Day 1 — contracts, then scaffolding

**Run the 30-minute kickoff** (SETUP.md Part 5). Do not skip it. Twenty minutes
agreeing four dataclasses buys you a week where nobody blocks on anybody, and
it is the highest-leverage half hour available to you.

Walk them through the four execution paths specifically. It is the thing most
likely to be built wrong, and the mistake is expensive to unwind: only the
**request** path is a Graph. Ambient work is triggered by rows arriving,
temporal work by deadlines passing, and institutions are separate processes.

Then: `agentcore create`, skeleton `app.py`, get `/invocations` answering
locally with a hardcoded response.

---

## Day 2 — wire it, then deploy it

### `graph/request_path.py`

```python
builder = GraphBuilder()
builder.add_node(intake_agent, "intake")
builder.add_node(household_swarm, "household")   # a Swarm is a valid node
builder.add_node(warden_agent, "warden")
builder.add_node(remedy_agent, "remedy")
builder.add_node(file_agent, "file")
builder.add_node(deferred_tail, "deferred")

builder.add_edge("intake", "household")
builder.add_edge("household", "warden")
builder.add_edge("warden", "remedy")
builder.add_edge("remedy", "file", condition=is_institutional)
builder.add_edge("remedy", "deferred", condition=lambda s: not is_institutional(s))
builder.set_entry_point("intake")
builder.set_execution_timeout(180)
```

**Wire it end to end with stubs on Day 2**, before anyone's agent is finished.
Never be in a state where half the system is unconnected — an integration you
defer to Thursday is an integration that eats Thursday.

`deferred` is not padding. It records that the mutual-aid and shared-cost tails
are designed and not built, keeps the fork visible in the trace, and is honest.

`result.accumulated_usage` gives you token cost per case for free. Log it — it
is evidence for the cost argument.

### Deploy today, not Day 4

`agentcore deploy`. First deploys always break. Broken on Tuesday costs an hour;
broken on Thursday costs the project.

### Gate

One claim in one end, one filing out the other, **on deployed infrastructure**.
Nothing deepens until that holds.

---

## Day 3 — observability, and the post nobody wants to write

Set up OTEL with `aws-opentelemetry-distro`, and **tag every span with
`case_id`** so traces group by case. That grouping is what makes the trace UI
possible, so do it before you build the UI.

`agents/digest.py`: decide what deserves a human, choose **one** recipient (not
everyone), compose in their language. This agent *is* the brief's "only pings
you when there's a real decision" — say that in the video.

**Draft the builder.aws post tonight**, while the decisions are fresh. It is
**+0.6 on a five-criterion scale** and it is always the thing that slips. Write
it Wednesday, publish Friday.

---

## Day 4 — make the invisible visible

**This is the day that decides your score, and it is not about polish.**

Almost everything good about Panchayat happens in a trace log, not on a screen:
the Warden refusing to leak an inference, Pattern Watch going four days without
invoking a model, the Watchdog disputing a closure using seven other households'
claims, the upgrade mutating a row. **Nothing that makes this project special
has a natural screen.**

So the demo surface is the trace, not a chat window. Build **one live case view**
where state changes with the responsible agent named beside each transition:

```
FILED       remedy      -> BWSSB (not BBMP)  [BWSSB Citizen Charter §…]
TRACKING    watchdog    -> SLA 7d, wake scheduled
PAUSED      watchdog    -> endpoint unreachable, clock held
UPGRADED    pattern     -> +9 households, tier 2, 4th failure since June
                           2 excluded: consent scope / different feeder
CLOSED      bwssb       -> "resolved - supply restored"
DISPUTED    watchdog    -> 7 live claims contradict closure
ESCALATED   watchdog    -> Assistant Executive Engineer
DECISION    digest      -> 1 question to 1 person
```

Also capture a **real ten-minute `RealClock` trace** to sit beside the compressed
one. That pairing is the entire rebuttal to "you faked the hard part" — show
`TIME_SCALE=86400` on screen and the real trace next to it.

---

## Day 5 — ship

**The video is Raghav's (14 Sep).** Its guidance moved to `docs/team/RAGHAV.md`,
and the project lives in `video/`.

---

## If Friday goes wrong

Cut in this order: escalation tiers 3 and 4 → the Warden's inference detection →
the trace UI's polish. **Cut the density curve last.** Almost nobody else will
have a number at all.

## Your lead duties

- Unblock before you build. Someone stuck for an hour costs more than your PR.
- Merge PRs same day. A long-lived branch is how four people lose Thursday.
- Ask each person for their gate result at end of day, not their vibe.
- If Alakshendra's routing accuracy is under 80% on Day 1, that is a group
  problem the same evening — not his problem alone on Thursday.
