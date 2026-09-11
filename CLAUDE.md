# Panchayat

Read this before doing anything in this repo. It is the shared context for four
people working in parallel, each with their own Claude session.

## What we are building

A neighbourhood agent mesh for the **AWS Agents for Humans hackathon, Good
Neighbor track**, built on the **Strands Agents SDK** and deployed to **Bedrock
AgentCore**. Context is urban India (Bengaluru, Ward 12).

**One line:** every household reports alone; the street gets the leverage.

**The problem is not discovery.** When the water fails, the building WhatsApp
group knows in fifteen minutes. What nobody has is the stamina to file against
the right body, track a statutory clock for eleven weeks, notice the day it
breaches, and climb to the next authority. This is documented, not invented:
Bengaluru citizens report BBMP tickets closed as "resolved" with no work done,
and one pothole complaint was opened and re-closed at least fifteen times.

**We do not fix pipes.** We pursue resolution. Never write "solves".

## The shape: four execution paths, not one process

This is the decision everything follows from, and the one most likely to be got
wrong. Only ONE of the four things this system does is request-scoped.

| Path | Trigger | Runs on |
|---|---|---|
| **Request** | a household reports | AgentCore Runtime, one Strands `Graph` |
| **Ambient** | a claim row arrives | Lambda on DynamoDB Streams |
| **Temporal** | a deadline passes | EventBridge Scheduler -> Lambda |
| **Institutions** | called over A2A | separate processes, **their own state** |

Do not try to model ambient or temporal work as Graph nodes. A Graph invocation
cannot wait seven days or react to a row arriving.

**Institutions must never touch our DynamoDB table.** Shared state would make
the trust boundary decorative. That separation is the point of using A2A.

## The spine runs at N=1

The individual path is the product and it is complete on its own. Clustering is
**ambient** -- it watches the claim stream and upgrades a case already in
flight when a pattern crosses threshold. It never gates anything, and on a
quiet street it invokes no model for weeks.

`SIGNAL -> DELIBERATE -> REPRESENT -> ACT -> TRACK -> ESCALATE -> CLOSE`

## Hard rules

1. **Nothing calls `datetime.utcnow()`.** Take time from `core.clock.get_clock()`.
   Both clock implementations drive the same Watchdog function. Never write
   `if demo_mode:` inside the Watchdog -- if you want to, the clock is wrong.
2. **`HouseholdPosition` never crosses the membrane.** Only `Claim` does, and
   only the Warden emits one.
3. **Jurisdiction is looked up, never generated.** A hallucinated authority
   reproduces the exact failure we claim to fix. Every routing decision carries
   a citation.
4. **Agents draft, humans sign.** No filing against a public body is submitted
   without a named person approving it. The liability lands on the household.
5. **Every institutional action is idempotent.** A retrying Watchdog that files
   twice produces a duplicate that reads as spam and gets both copies closed.
6. **Merges are reversible.** Keep provenance in `case.merged_from`.
7. **Aggregation points outward only.** Collective pressure may be assembled
   against an institution, never against a person or household.
8. **No autonomous police filing.** Read, track, advise only.
9. **We promise minimisation, not anonymity.** Eight houses on a cross street
   means any claim precise enough to file is precise enough to identify. What
   we guarantee is that income, health, arrears and schooling never cross.
10. **`core/types.py` is frozen.** Raise changes in the group before editing.

## Verified API surface

Checked against the docs **and against the installed packages** on 10 Sep 2026:
`strands-agents 1.55.0`, `strands-agents-tools 0.8.8`, `bedrock-agentcore 1.22.0`.
Every import below was executed, not remembered. Versions are pinned in
`requirements.txt` -- raise it in the group before bumping.

Note `Swarm` takes keyword-only arguments after `nodes`.

Copy these shapes rather than recalling them.

```python
from strands.multiagent import GraphBuilder, Swarm
from strands.multiagent.a2a import A2AServer
from strands.agent.a2a_agent import A2AAgent
from bedrock_agentcore.runtime import BedrockAgentCoreApp

builder = GraphBuilder()
builder.add_node(agent, "id")
builder.add_edge("src", "dst", condition=lambda state: ...)  # state.results["src"].result
builder.set_entry_point("id")
graph = builder.build()
result = graph(payload)   # .status .execution_order .results .accumulated_usage

swarm = Swarm([a, b, c], entry_point=a, max_handoffs=6,
              execution_timeout=90.0, node_timeout=30.0)

A2AServer(agent_factory=make_agent, host="0.0.0.0", port=9001).serve()
remote = A2AAgent(endpoint="http://localhost:9001")

app = BedrockAgentCoreApp()
@app.entrypoint
def invoke(payload): ...
app.run()   # POST /invocations on :8080
```

`Swarm` maintains a **mutable `SharedContext` every agent reads and writes**.
That is correct inside one household and catastrophic across households -- it is
the verified reason the mesh uses A2A rather than a bigger swarm.

## Bedrock: which region, which model

Probed 10 Sep 2026, all three regions, both vendors.

- **Models run in `us-east-1`.** `ap-south-1` has **no Anthropic inference
  profiles at all** -- our data stays in ap-south-1, the model calls do not.
- **Use the region-prefixed inference profile ID, never the bare model ID:**
  `us.anthropic.claude-sonnet-5` for reasoning nodes,
  `us.anthropic.claude-haiku-4-5-20251001-v1:0` for cheap ones.
- **Claude 3.5 is dead.** It returns `ResourceNotFoundException: This model
  version has reached the end of its life`. Do not copy it from a blog post.
- **The block is only the model data plane. AgentCore is live.** Probed
  10 Sep: Runtime, Memory, Gateway, Identity and Code Interpreter all answer
  clean. Our deploy target was never blocked -- and that is the part the
  hackathon grades. Do not plan around losing it.
- **What IS blocked:** every `bedrock-runtime` invoke returns
  `ValidationException: Operation not allowed`, all vendors, all regions,
  while the control plane happily lists 120 models. Listing is not access.
  Account-level authorization, not IAM and not model access; nothing in the
  console fixes it. Support case 178898467100367.
- **Read the error, it tells you which problem you have.**
  `AccessDeniedException` = your IAM user is missing a policy, you can fix it.
  `ValidationException: Operation not allowed` = the account, you cannot.
  We wasted a day conflating the two.

## Clustering without embeddings

Settled 10 Sep after the 0.65 ceiling turned up. Read this before touching
`core/scoring.py`.

**A missing embedding means the semantic term is UNAVAILABLE, not zero.**
Score it as zero and the ceiling is `0.40 + 0.25 = 0.65`, below `TAU = 0.72`.
Two houses on one trunk main reporting the same fault a minute apart score a
perfect 1.0 on both components that ran and still never cross. Nothing errors,
nothing logs; Pattern Watch just never fires and you lose Day 3 hunting a bug
that is a missing field.

So: drop the term and renormalise over the weights that did run.

```python
if a.embedding is None or b.embedding is None:
    total = (W_TOPOLOGY * topo + W_RECENCY * rec) / (W_TOPOLOGY + W_RECENCY)
    semantic_available = False
```

This degrades safely: the decoy on the other feeder scores topology 0, so its
renormalised ceiling is 0.385 and it still does not cluster.

**`CorrelationScore.semantic_available` must reach the trace UI.** While
Bedrock is blocked, EVERY cluster forms this way. A demo that shows clusters
without saying semantic never ran is claiming agreement it did not compute,
and that is the kind of thing a judge asks about.

### Where embedding does NOT go: `put_claim()`

Tempting and wrong. `core/db.py` requires both backends to behave the same, so
embedding on write means `memstore` embeds too -- which puts a Bedrock call in
the offline test suite and takes it from green to unrunnable, today, on a
blocked account. It also drops a network call, a cost and a failure mode into
the storage layer, on the household's request path, for a value nothing reads
until the ambient pass runs.

**Embed in the ambient Pattern Watch Lambda**, on the stream record, off the
request path, where it can retry and where a failure degrades to the
renormalised score instead of losing the claim. Storage stores.

### Floats do not go into DynamoDB

`to_dict()` passes `list[float]` straight through and boto3 refuses it:
`TypeError: Float types are not supported. Use Decimal types instead.` The
obvious fix is a `Decimal` per element, and that is the trap -- measured, a
1024-dim vector becomes **~32KB** of full-precision Decimals per claim against
a 400KB item ceiling, on every write.

**Pack as base64 float16: ~2.7KB, twelve times smaller.** Correctness first,
and the cost story survives.

## Scope for the five days

**Built:** institutional tail only, text intake, 9 agents, one ward of curated
jurisdiction data, calibrated institution simulators, the eval harness.

**Designed, drawn, not built:** mutual-aid and shared-cost tails, voice and
vernacular, per-member privacy inside a household, cross-neighbourhood
federation. Say so plainly -- naming your own compromises reads as judgement.

## Ownership

| Who | Lane | Owns |
|---|---|---|
| **Ali** | platform + lead | `graph/`, `app.py`, deploy, observability, trace UI, `agents/digest.py`, video |
| **Kartik** | data + mesh | `core/store.py`, `core/scoring.py`, `agents/pattern_watch.py`, `agents/anti_abuse.py`, corpus, tau sweep, density curve |
| **Alakshendra** | institutions | `data/jurisdiction/`, `agents/remedy.py`, `institutions/`, routing accuracy |
| **Raghav** | household + time | `core/clock.py`, `agents/intake.py`, `agents/household.py`, `agents/warden.py`, `agents/watchdog.py` |

Your brief is in `docs/team/<YOURNAME>.md`. Read it and this file, then start.

**Stay in your own files.** Ownership follows the membrane, so the A2A
boundaries are also the merge boundaries. If you need something from another
lane, use the agreed signature in the stub and let them fill it in.

## Nobody waits for anybody

Four people, five days, and real dependencies between the lanes. The rule that
stops that turning into idle time:

**You depend on a contract, never on a person's implementation.**

Every cross-lane dependency already has a fake, shipped and tested:

| You need | Don't wait for | Use |
|---|---|---|
| storage | Kartik's `store.py` | `from core.db import ...` (memory backend by default) |
| a `Claim`, `Case`, `HouseholdPosition` | whoever owns that agent | `core/fakes.py` |
| the 12-household outage scenario | Pattern Watch | `fakes.the_outage()` |
| jurisdiction entries | nothing, it landed 10 Sep | `from agents.remedy import lookup, resolve` — 31 curated entries. The sample is dead and the loader ignores it. |
| a compressed clock | nothing | the `clock` fixture in `tests/conftest.py` |

```bash
pytest                                 # memory backend, no AWS, 0.03s
PANCHAYAT_BACKEND=dynamodb pytest      # the real table, same tests
```

**The same tests run against both backends.** If a test passes on memory and
fails on DynamoDB, the DynamoDB one is wrong, and we find that out on our own
bench rather than during integration on Thursday.

The whole system runs offline with `PANCHAYAT_BACKEND=memory`, which matters
more than we planned: Bedrock authorization is still pending on our account.

**If you find yourself blocked on another lane, that is a bug in the fakes.**
Say so in the group and we add one. Do not sit waiting, and do not reach into
someone else's file.

## Coordination

**Two syncs a day, fifteen minutes each. No standups.**

- **Morning:** what is your gate today. One falsifiable thing, not a plan.
- **Evening:** did the gate pass. **Report the result, not the vibe.** "Routing
  came in at 62%" is useful on Tuesday and catastrophic on Thursday.

**Blocked for thirty minutes? Post it.** An hour lost to being stuck privately
costs more than any interruption.

**`STATUS.md` is the shared brain.** Update your row when something lands.
Your teammates' Claude sessions cannot see yours, so that file is how their
Claude learns that `store.py` is real and what shape it took. Ten seconds,
and it prevents someone rebuilding what already exists.

**Merge to `main` daily.** A branch that lives three days is a merge conflict
with legs. Ali merges same day.

## Nothing reaches main unreviewed

Settled 10 Sep. Applies to everyone including Ali.

1. **Work on a branch.** The pre-commit hook refuses `main`. Lane prefixes:
   `feat/plat-*` `feat/mesh-*` `feat/inst-*` `feat/hh-*`.
2. **Run `/code-review` on your branch before you ask a human to look.** Fix
   what it finds, or say why you disagree. Do not spend a teammate's attention
   on something a machine would have caught.
3. **Push it and post it in the group.** Everyone gets the chance to look --
   that is the point, not four sign-offs.
4. **Then merge, by this bar:**

| Change | Bar before merge |
|---|---|
| Normal lane work | posted + `/code-review` clean + a look from the lane that **consumes** it |
| `core/types.py`, the hard rules, `requirements.txt` | **all four, explicitly.** Everyone codes against these |
| Red suite, broken `main`, a blocker on someone else | **merge now, tell the group after** |

**Silence is assent, not a veto.** A branch that waits for the slowest reviewer
lives overnight, and a branch that lives three days is a merge conflict with
legs. If you need someone's eyes specifically, say whose and say why.

**The last row is not a loophole, it is the point.** On 10 Sep a failing clock
test sat flagged-but-unfixed because it straddled two other people's files,
while everyone else read a red suite as their own breakage. Making that wait
for four approvals makes the blocked teammate wait longer.

**Reviewing outside your lane is still worth it.** You will not out-argue
Alakshendra on which body owns a borewell. You will absolutely catch a missing
clock call, a swallowed exception, or a claim crossing the membrane -- and
those are the bugs that actually sink us.

## Definition of done for any module

- The stub's `NotImplementedError` is gone
- It takes time from `Clock`, not the system clock
- It has one pytest in `tests/` that runs without AWS credentials
- `ruff check .` is clean -- against `ruff.toml`, with `ruff==0.16.6` from
  `requirements.txt`. Both are pinned deliberately: ruff's default rule set
  changes between releases, so before this existed the four of us each ran a
  different ruff, each honestly reported clean, and the merged tree had 42
  errors. The selection is about bugs, not formatting, and `DTZ` is in it so
  that **hard rule 1 is now enforced by the linter** rather than remembered.
  Bumping either is a group call.
