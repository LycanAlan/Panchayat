# Panchayat, explained plainly

**Read this if you need to understand the project or explain it to someone, and
you have not read the code.** No jargon that is not unpacked. Every number in
here was measured on 13 Sep 2026 by running the suite or querying the live
table, not recalled.

If you need the *evidence* for a specific claim — which file, which line —
that is the companion document: [`docs/demo/docket.html`](demo/docket.html),
forty questions each with the file that proves it. Open it in a browser.

---

## What the thing does

You have no water. You complain. Normally one of two things happens: you file it
to the wrong department and it quietly dies, or you file it correctly and then
forget to chase it, and it quietly dies.

**Panchayat is software that does the chasing.** It works out which office is
actually responsible, writes the complaint letter, remembers the legal deadline,
notices the day that deadline passes, and escalates to the next-senior officer.
For weeks. Without you remembering anything.

And when several neighbours complain about the same pipe, it joins their
complaints together — because one person saying the tap is dry is easy to
dismiss, and seven people with timestamps is not.

**We do not fix pipes. We pursue the complaint.** Never write "solves".

---

## 1. Why "AI agents" and not just a form?

**An agent here means: a small program with one job, that is allowed to say
"I don't know."** We have eight of them.

Storing a complaint is easy — a form and a database does that. The hard parts
are all judgement calls:

- Which of thirty-one offices is responsible for *this* street?
- Are my neighbour and I reporting one problem, or two?
- The office marked this "resolved" — did they actually do anything?
- Has the legal deadline passed, and who is next up the chain?

Each of those gets its own agent that can refuse. The routing agent returns
*"I don't know, ask the user"* instead of guessing. The anti-abuse agent can veto
a merge that the maths proposed. A workflow engine has no way to express
"decline, and here is why."

### Where the AI model actually gets used

This surprises people, so be precise about it. **There are only four places a
language model is called:**

1. Reading messy text — and *only* when one sentence contains more than one
   problem. A normal single complaint never calls a model.
2. Working out what the household as a group wants.
3. Deciding whether two neighbours' complaints are genuinely the same fault.
4. Turning text into numbers, for similarity matching.

And there are three places where a model is **banned forever**, written into the
code:

- **The privacy filter.** A model there could improvise a leak.
- **The office lookup.** A model there would invent an office name. That is the
  exact disaster we exist to prevent.
- **The anti-abuse checker.** The text it is policing was written by the
  household, and a model reading it could be *talked into* approving the very
  thing it is meant to block.

**Right now the model is not running at all.** AWS has not enabled model access
on our account — it is an account-level block, not something a setting fixes.
The system still completes every complaint end to end; it just reads text less
cleverly. **That costs quality, not availability**, and we should say so plainly
rather than hide it.

---

## 2. Who receives the complaint?

Not "BWSSB" the organisation. **A specific officer** — *"BWSSB Assistant
Engineer, sub-division office."* Naming the actual desk is most of what makes a
complaint land.

The journey:

```
you type the problem
   -> system pulls out what the problem is
   -> decides what is safe to share outside the household
   -> looks up who is responsible  ->  BWSSB (not BBMP)
   -> writes a draft letter to the named officer
   -> *** a real person presses approve ***
   -> only now is it sent to the office
   -> a deadline reminder is booked
```

**The system never sends anything by itself.** That is a hard rule: agents
draft, humans sign. The approval is tied to one person's ID — not the household
— because "the household agreed" is not a signature anyone can be held
responsible for. Approving also does not send it: recording an approval and
handing paper to a government office are two separate acts, and collapsing them
would put a network call behind a click.

Right now those five offices are **simulators we wrote**. They are deliberately
difficult, not cooperative:

| The water board desk | Rate | Why that number |
|---|---|---|
| Misses the statutory deadline | 45% | Sakala carries over one lakh overdue applications |
| Falsely marks it "resolved" | 30% | reported Sahaaya / BBMP ticket behaviour |
| Rejects as malformed | 15% | missing or mismatched RR number |
| Unreachable, portal down | 8% | observed grievance-portal downtime |

That is the environment the chasing logic had to survive. A simulator that always
says yes would make the whole demo a puppet show — so a desk profile with no
sourced note for its rates refuses to load at all.

---

## 3. It is synthetic and there is no GPS — so how does it know which office?

**By a street code, not a map.** Something like `ward12-4thcross`.

We hand-wrote **31 of these**, each with the correct office, the legal deadline,
the escalation chain and a citation. Plus **74 ways people actually write the
street name** — "4th cross", "fourth cross", "4th cross road" — so messy text
still finds the right row.

If the street is not in the table, the system **says it does not know and asks.**
It never guesses.

Three things worth knowing:

**The table is not a trick.** 25 of the 31 streets answer BWSSB, but 3 answer
BBMP and 3 answer a private builder. The BBMP ones are villages absorbed into the
city in 2008 that were on local borewells before the Cauvery network reached
them — so the correct answer depends on which side of an old boundary your house
sits, which nobody living there could possibly know. That is exactly the kind of
question this software should answer for you. It also means the routing
evaluation has something real to measure: a stub that always answered "BWSSB"
would score 80%, not 100%.

**Distance is the wrong signal; the pipe is the right one.** Two houses fifty
metres apart on different water mains have two different problems. Two houses
four hundred metres apart on the same main have one. So every street records its
pipe ID, and there are 9 pipes across the 31 streets.

**The honest gap:** something has to tell us the street code. There is no
user-registration system yet — nothing in the project stores a household record.
So the street code arrives with each request. In a real product that is an
address lookup or a one-time sign-up. Here it is a field, and we say so. When it
is missing, the answer says `no_segment` rather than failing quietly five steps
later.

---

## 4. Is it all hard-coded? What do the tests prove?

"Hard-coded" means three different things here, and only one of them is a
criticism.

**Hard-coded on purpose:** the office list, the escalation chains, the street
aliases. This is the one thing a model is forbidden to generate, so of course it
is a fixed table.

**Tuned, not guessed:** the matching threshold and the scoring weights. A script
sweeps for the right value. The source comment literally says *"do not hardcode a
defended number."*

**The real weak spot:** while the model is switched off, some steps return canned
answers. This is genuine, and the system **labels those steps `STUB` in its own
output**, so anyone watching the demo can see which parts are real. That is the
design: the trace tells the truth about itself, including about itself.

**Not hard-coded at all:** which office gets chosen, the case state machine, the
escalation tier, the deadline arithmetic, the duplicate-prevention keys, the
storage layout. And there is no `if demo_mode:` anywhere in the project.

### The tests

**522 pass, 37 are skipped.** Always say both numbers — a skipped test is not a
passing test, and "522 passed" on its own overstates the position by exactly 37.

The 37 skipped ones all need a real AWS database and run separately. They are the
second half of a rule we follow: **the same tests run against the fast in-memory
storage and against the real database.** That has already caught a real bug — one
function existed only in the fast version, so the queue that surfaces a stuck
household to a person worked offline and nowhere else, and nothing failed until
somebody ran the suite against a real engine.

What the tests prove is the stuff you cannot show in a demo: the deadline
passing, the office lying, a duplicate being sent twice, a desk that never
answers, private data trying to leave.

The test that earned its keep most is the least glamorous one. Three tests
checking the AWS permission settings caught a policy pointing at the **wrong AWS
region** after we moved. That would not have failed at deployment. It would have
failed weeks later, at the first deadline — during the demo.

---

## 5. Where does everything get stored?

**One AWS database table called `panchayat`, in Hyderabad, India.** It has 28
rows in it right now, all from real use of the deployed system — not test data.

Six kinds of row:

| Row | What it holds |
|---|---|
| **claim** | what the household reported, after privacy filtering |
| **case** | status, escalation level, deadline |
| **filing** | the actual letter, and who signed it |
| **filing pointer** | lets you sign a letter without knowing its case |
| **case-by-pipe** | who else is on this water main |
| **unsigned** | the queue of letters waiting for a human |

Logs go to AWS CloudWatch, and **every log line carries the case ID** — so one
search reconstructs an entire eleven-week story across every part of the system.

**Nothing runs when nothing is happening.** No background loop, no polling. A
reminder is booked as a single dated alarm named after the case, and it deletes
itself after firing. On a quiet street this system costs storage and nothing
else.

Why Hyderabad and not Mumbai: the AWS agent quota is **per-region**, and it is
zero in four regions we tried and at the full default in Hyderabad. Data staying
in India is a happy side effect of that, not the original reason. The model calls
are not in India and never were — the Mumbai region has no Anthropic models at
all.

---

## Other things people will ask

**Is it actually deployed, or is this a laptop demo?**
Deployed. Proven by filing a real complaint at the live address and watching the
database change on its own: a reminder was booked, the reminder fired, and the
case moved from "drafted" to "dormant" because nobody signed it in time. The one
thing still on a laptop is the five simulated offices — a cloud server cannot
reach `localhost`. **Decide how to handle that before recording the video, not
during it.**

**What about privacy?**
Only a "claim" leaves the household. Income, health, debts and schooling never
cross that line, ever. We promise **minimisation, not anonymity**, and that
distinction is deliberate: with eight houses on a cross street, any complaint
precise enough to file is precise enough to identify someone. Claiming anonymity
would be a lie you could check.

The outward-facing read API is built from an **allowlist** — it names the fields
it publishes — rather than by deleting fields from the full object. That is not
stylistic. A deny-list means every new field is published by default until
somebody remembers to redact it.

**Could this be turned against a neighbour?**
No, and it is enforced in the data rather than promised in the README. The
residents' association appears in one escalation chain and has **no filing
desk**, with the reason written in the file: *"the RWA is a neighbour, not an
institution."* Pressure points outward at institutions only.

**Does it contact the police?**
Never. Read, track, advise only.

**Anyone can approve anything — is that not a hole?**
Yes, and it is the biggest one. There is no login. Anyone who can reach the
endpoint can approve any letter by typing any member ID. **The frontend team must
know this** — a screen that lets someone type their own ID makes the signature
meaningless.

**You compress time for the demo. Is that not cheating?**
It would be, if the compressed version were different code. It is not — both
modes drive the *same* chasing function, and adding a demo-only branch to it is
explicitly forbidden. Even the simulated offices read the same clock, because an
office answering on real time while the chaser runs at 86,400× would never reply
inside a window, and the demo would be measuring nothing.

**What is not finished?**
Six things: no login; the offices are on localhost; model access still blocked by
AWS; the visual trace screen does not exist yet; you can only list open
complaints, not resolved ones; and a handful of smaller known gaps. All six are
written down in [`docs/handoff/status-2026-09-13.md`](handoff/status-2026-09-13.md)
so nobody discovers them on camera.

---

## The numbers, in one place

| | |
|---|---|
| Agents | **8**, plus 5 simulated offices across the A2A boundary |
| Execution paths | **4** — request, ambient, temporal, institutions. 3 deployed |
| Strands patterns used | **4** — Swarm, Graph, Agents-as-Tools, A2A |
| Jurisdiction entries | **31** streets, 9 pipes, 74 aliases, 3 escalation chains |
| Tests | **522 passed, 37 skipped**, ruff clean |
| Live table | **28 rows**, ap-south-2, streams on |
| Model calls on the deployed spine | **0 tokens** — account blocked |
