"""Prove every DEPLOYED desk answers over A2A, end to end.

    python scripts/smoke_desks.py             # every desk found in the region
    python scripts/smoke_desks.py ward school # just these

Discovers the runtimes by name (`panchayat_desk_<desk>`), addresses each one
the way the deployed Watchdog does -- boto3 `InvokeAgentRuntime` carrying
JSON-RPC, per institutions/client.py -- and files one marked smoke complaint.

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

#: Enough attempts that a desk with a 5% simulated downtime is very unlikely
#: (1 in 8000) to be reported down for that reason alone.
ATTEMPTS = 3

#: A live desk answered. See "WHAT COUNTS AS PASS" above.
ANSWERED = ("ACCEPTED", "DUPLICATE", "REJECTED")


def discover(region: str) -> dict[str, str]:
    """Deployed desks, by desk name -> runtime ARN."""
    import boto3

    client = boto3.client("bedrock-agentcore-control", region_name=region)
    found: dict[str, str] = {}
    token = None
    while True:
        kwargs = {"nextToken": token} if token else {}
        page = client.list_agent_runtimes(**kwargs)
        for runtime in page.get("agentRuntimes", []):
            name = runtime.get("agentRuntimeName", "")
            if name.startswith(PREFIX):
                found[name[len(PREFIX):]] = runtime["agentRuntimeArn"]
        token = page.get("nextToken")
        if not token:
            return found


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
    last = ("UNREACHABLE", "no attempt made")
    for _ in range(ATTEMPTS):
        reply = InstitutionClient().send(desk, instruction(desk))
        name = reply.outcome.name
        last = (name, (reply.ref or reply.detail or "").strip())
        if name in ANSWERED:
            return last
    return last


def main(argv: list[str]) -> int:
    runtimes = discover(REGION)
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
