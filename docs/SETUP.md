# Setup

Everything below happens **before** anyone writes a line of agent code. Budget
45 minutes. Ali does the shared AWS setup once; everyone else does the local
setup on their own machine.

---

## Part 1 — Ali only, once, before the others start

These are the things that block other people, so do them first.

### 1.1 AWS account

One account, shared. Do **not** have four people each create their own — the
DynamoDB table, the Bedrock model access and the AgentCore runtime all need to
be the same one, and reconciling four accounts on Day 4 is a lost afternoon.

- [ ] AWS account with billing enabled
- [ ] Apply the **$50 hackathon credits** (Devpost Resources tab → request form).
      Do this *now*, not on Day 3 — approval is not instant.
- [ ] Region: **us-east-1**. Pick one and never deviate; Bedrock model
      availability differs by region and cross-region debugging is a tax.

### 1.2 Bedrock model access

Console → Bedrock → **Model access** → request access. Enable at minimum:

- Amazon Nova Lite
- Anthropic Claude Haiku 4.5
- Anthropic Claude Sonnet (whichever current version is offered)
- **Amazon Titan Text Embeddings V2** ← Kartik is blocked without this

**Then copy the exact inference-profile IDs into `.env`.** They carry a region
prefix like `us.anthropic.…`. A wrong ID is a twenty-minute detour you will
take at the worst possible moment. Confirm them in the console, do not trust
any ID written in a doc — including ours.

### 1.3 IAM users

Create **four** IAM users, one each, with programmatic access. Do not share one
key four ways — when something gets deleted you want to know who did it.

Attach this policy to all four (hackathon-grade, deliberately broad):

```
AmazonDynamoDBFullAccess
AmazonBedrockFullAccess
CloudWatchLogsFullAccess
AmazonEventBridgeSchedulerFullAccess
AWSLambda_FullAccess
```

Plus the AgentCore permissions from the AWS docs for the runtime role.

Send each person their **access key ID + secret** over something private. Not
the group chat, not this repo, not a screenshot in the Devpost submission.

### 1.4 The shared table

```bash
aws dynamodb create-table \
  --table-name panchayat \
  --attribute-definitions \
      AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
      AttributeName=GSI1PK,AttributeType=S AttributeName=GSI1SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes \
      'IndexName=GSI1,KeySchema=[{AttributeName=GSI1PK,KeyType=HASH},{AttributeName=GSI1SK,KeyType=RANGE}],Projection={ProjectionType=ALL}' \
  --billing-mode PAY_PER_REQUEST \
  --stream-specification StreamEnabled=true,StreamViewType=NEW_IMAGE \
  --region us-east-1
```

The stream is what triggers Pattern Watch. Kartik needs it on from the start.

### 1.5 GitHub

- [ ] Create a **private** repo `panchayat` under your account
- [ ] Add Kartik, Alakshendra, Raghav as collaborators with write access
- [ ] Push `main` (see §4)
- [ ] Protect `main`: no direct pushes, PRs only, one approval

---

## Part 2 — everyone, on their own machine

### 2.1 Tools

| Tool | Version | Check |
|---|---|---|
| Python | 3.10+ (we have 3.12) | `python --version` |
| Git | any recent | `git --version` |
| AWS CLI v2 | latest | `aws --version` |
| Node | 18+ (Ali only, for the trace UI) | `node --version` |

**AWS CLI is not installed on Ali's machine yet.** Windows:
`winget install -e --id Amazon.AWSCLI` then reopen the terminal.

### 2.2 Clone and install

```bash
git clone https://github.com/<ali>/panchayat.git
cd panchayat
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS:    source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2.3 Credentials

```bash
aws configure --profile panchayat
# paste your own access key + secret
# region: us-east-1
# output: json
```

Then in `.env` set `AWS_PROFILE=panchayat` and paste the model IDs Ali confirmed.

### 2.4 Verify you are actually set up

```bash
python -c "import strands, bedrock_agentcore, boto3, numpy; print('deps ok')"
aws dynamodb describe-table --table-name panchayat --region us-east-1 --query 'Table.TableStatus'
aws bedrock list-foundation-models --region us-east-1 --query 'length(modelSummaries)'
python -c "from core.types import Claim; from core.clock import get_clock; print('contracts ok', get_clock().now())"
```

All four must pass before you start. If `describe-table` fails, your IAM user is
wrong — say so in the group rather than working around it.

---

## Part 3 — no keys needed for these

Worth knowing so nobody goes hunting:

- **Strands Agents SDK** — open source, no key
- **A2A servers** — plain HTTP on localhost:9001-9004, no auth for the demo
- **The institution simulators** — ours, no external calls
- **WhatsApp / Twilio** — **not needed.** Intake is text via a simple endpoint.
  Voice and vernacular are out of scope for five days; do not let anyone start
  a Twilio trial.

---

## Part 4 — branching

```
main                      protected, always green
  feat/mesh-<thing>       Kartik
  feat/inst-<thing>       Alakshendra
  feat/hh-<thing>         Raghav
  feat/plat-<thing>       Ali
```

Small PRs, merge often. With four people on a five-day clock, a long-lived
branch is how you lose Thursday.

Commit messages end with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Part 5 — Day 1 morning, together, 30 minutes

Do not skip this. It is the highest-leverage half hour of the week.

1. Ali walks through `CLAUDE.md` — especially the four execution paths
2. Everyone reads `core/types.py` out loud-ish and **objects now** if a field
   is wrong. After this meeting it is frozen.
3. Confirm the Bedrock model IDs together and paste into `.env`
4. Everyone runs the four verification commands in §2.4
5. Agree the two Day 1 gates:
   - Alakshendra: 50 labelled complaints routed, target ≥80%
   - Kartik: table live with GSI1, `put_claim` + `claims_in_window` working

Then split.
