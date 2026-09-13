"""Prove every DEPLOYED desk answers over A2A, end to end.

    python scripts/smoke_desks.py             # every desk found in the region
    python scripts/smoke_desks.py ward school # just these

Discovers the runtimes by name (`panchayat_desk_<desk>`), addresses each one
over the transport the deployed Watchdog uses -- boto3 `InvokeAgentRuntime`
carrying JSON-RPC, per institutions/client.py -- and files one marked smoke
complaint.

WHAT IT DOES NOT COVER. It calls `send()` with an instruction of its own, not
`InstitutionClient.file()`, so the signature gate and the JSON fencing that
file() puts around citizen-authored text are NOT exercised here. A regression
in file() would leave every desk answering ACCEPTED to this script while every
real filing failed. This checks that a desk is deployed, reachable and
answering; it is not a test of the filing path.

WHAT COUNTS AS PASS, AND WHY IT IS NOT "ACCEPTED"
A desk answering ACCEPTED or DUPLICATE has done the whole chain: SigV4 in,
A2A parsed, a model call to choose the tool, the Desk's own judgement, a write
to the desk's own DynamoDB table under its own role, and a reply in the one
grammar every caller parses. DUPLICATE on a re-run is the stronger result of
the two -- it means the checkpoint outlived the microVM that wrote it, which
is the entire reason institutions/desk_store.py exists.

REJECTED is also a live desk. It is the calibrated refusal of a filing missing
particulars, which is behaviour, not breakage.

UNREACHABLE IS THE ONE THAT NEEDS CARE. Every profile carries an
`unreachable_rate` (0.05 on ward), so a desk is DESIGNED to simulate downtime
on about one call in twenty. Reporting the first UNREACHABLE as a failed deploy
would be the same misdiagnosis that cost us an hour on bwssb, where a calibrated
REJECTED was read as a dead endpoint. So each desk is retried, and only a desk
that never answers across all attempts is called down.

Owner: Ali (platform). Touches no case of ours and no table but the desks' own.
"""
from __future__ import annotations

import os
import pathlib
import sys

# `python scripts/smoke_desks.py` puts scripts/ on sys.path, not the repo root,
# so `institutions` would not import. Added here rather than asking every caller
# to set PYTHONPATH, which is the kind of instruction that gets left out of the
# one command someone copies at 2am.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

REGION = os.environ.get("AWS_REGION", "ap-south-2")
PREFIX = "panchayat_desk_"

#: Retries before a desk is called down. Judge this against the WORST desk,
#: not the best: vendor carries `unreachable_rate: 0.10`, the highest of the
#: five, so three attempts is 0.10^3 -- about 1 run in 1000 reporting a
#: spurious DOWN, or 1 in 800 across all five. (The first draft of this comment
#: quoted 1 in 8000, which is ward's 0.05 and the most flattering desk.)
ATTEMPTS = 3

#: A live desk answered. See "WHAT COUNTS AS PASS" above.
ANSWERED = ("ACCEPTED", "DUPLICATE", "REJECTED")


def discover(region: str) -> tuple[dict[str, str], list[str]]:
    """Deployed desks by name -> runtime ARN, plus any strays.

    A runtime whose name carries the prefix but is not one of the five known
    desks -- a leftover, a rename, a sixth desk deployed before client.py knows
    about it -- is NAMED and skipped rather than probed. Probing it would look
    up an environment variable that does not exist and abort the whole run on a
    bare KeyError, so one stray runtime would hide the state of every desk
    after it in the loop.
    """
    import boto3

    from institutions.client import RUNTIME_ARN_ENV

    client = boto3.client("bedrock-agentcore-control", region_name=region)
    found: dict[str, str] = {}
    strays: list[str] = []
    token = None
    while True:
        kwargs = {"nextToken": token} if token else {}
        page = client.list_agent_runtimes(**kwargs)
        for runtime in page.get("agentRuntimes", []):
            name = runtime.get("agentRuntimeName", "")
            if not name.startswith(PREFIX):
                continue
            desk = name[len(PREFIX):]
            if desk in RUNTIME_ARN_ENV:
                found[desk] = runtime["agentRuntimeArn"]
            else:
                strays.append(name)
        token = page.get("nextToken")
        if not token:
            return found, strays


def instruction(desk: str) -> str:
    """One filing, with the particulars a calibrated desk asks for.

    `duration` and `affected` are not decoration: institutions/server.py
    refuses a body missing either, at the profile's `reject_malformed_rate`.
    A smoke test that left them out would measure that rate instead of the
    deployment.
    """
    from institutions.server import load_profile

    profile = load_profile(desk)
    service = (profile.accepts_services or ["general"])[0]
    return (
        "Call the accept tool with case_id='case_smoke_" + desk + "', "
        "service='" + service + "', "
        "body='SMOKE TEST, not a real complaint. Duration: 2 days. "
        "Affected: 1 household. Deployment check only.', "
        "idempotency_key='smoke-" + desk + "'"
    )


def probe(desk: str, arn: str) -> tuple[str, str]:
    """Outcome and detail for one desk, retried past simulated downtime."""
    from institutions.client import RUNTIME_ARN_ENV, InstitutionClient

    os.environ[RUNTIME_ARN_ENV[desk]] = arn
    # Both are loop-invariant. Building the client once also keeps the cached
    # boto3 client it holds, and makes the retries a truer replay of one caller
    # retrying -- which is what the Watchdog does.
    client = InstitutionClient()
    text = instruction(desk)
    last = ("UNREACHABLE", "no attempt made")
    for _ in range(ATTEMPTS):
        reply = client.send(desk, text)
        name = reply.outcome.name
        last = (name, (reply.ref or reply.detail or "").strip())
        if name in ANSWERED:
            return last
    return last


def main(argv: list[str]) -> int:
    runtimes, strays = discover(REGION)
    for name in strays:
        print("  " + name + " -- prefixed but not a known desk, skipped")
    if not runtimes:
        print("No " + PREFIX + "* runtimes in " + REGION + ".", file=sys.stderr)
        return 1

    wanted = [d.lower() for d in argv] or sorted(runtimes)
    missing = [d for d in wanted if d not in runtimes]
    for desk in missing:
        print("  " + desk.ljust(10) + "NOT DEPLOYED")

    down = list(missing)
    for desk in wanted:
        if desk in missing:
            continue
        outcome, detail = probe(desk, runtimes[desk])
        print("  " + desk.ljust(10) + outcome.ljust(13) + detail)
        if outcome not in ANSWERED:
            down.append(desk)

    print("")
    if down:
        print("DOWN after " + str(ATTEMPTS) + " attempts: " + ", ".join(down))
        return 1
    print("All " + str(len(wanted)) + " desks answered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
