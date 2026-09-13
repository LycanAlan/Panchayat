"""Durable ticket state for a desk that runs on AgentCore Runtime.

WHY THIS EXISTS. A `Desk` keeps its tickets in a local dict, and that is the
design, not an oversight: the institution owns its own state and must never
touch our table (CLAUDE.md). On a laptop the process lives as long as the demo
does. On AgentCore Runtime it does not -- sessions are short-lived microVMs --
so a ticket issued on Monday is gone by the time the Watchdog polls it on
Thursday, and `status()` answers UNKNOWN. That reads as "the office lost your
complaint", which is the exact failure this project exists to pursue, invented
by our own hosting.

So the desk checkpoints its own dict into the DESK'S OWN table, one item per
desk. `PANCHAYAT_DESK_TABLE` names it, and this module refuses to write to the
table our cases live in.

OFF BY DEFAULT. With `PANCHAYAT_DESK_TABLE` unset -- every local run and the
whole test suite -- `load()` and `save()` do nothing and the desk behaves
exactly as it always has: a dict in memory, no AWS, no network.

Owner: Ali (platform), in the institutions lane. Alakshendra owns the desk
behaviour itself; this only persists what that behaviour produces.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from institutions.server import Desk, Ticket

#: Written only when set. See "OFF BY DEFAULT" above.
TABLE_ENV = "PANCHAYAT_DESK_TABLE"

#: Our own table, which a desk may never write to. Read here so that a
#: misconfiguration is refused rather than quietly making the trust boundary
#: decorative.
OUR_TABLE_ENV = "PANCHAYAT_TABLE"

_table: Any = None


def table_name() -> str:
    return os.environ.get(TABLE_ENV, "").strip()


def _open():
    """The desk's table, or None when persistence is off."""
    global _table
    name = table_name()
    if not name:
        return None
    ours = os.environ.get(OUR_TABLE_ENV, "panchayat").strip()
    if name == ours:
        raise ValueError(
            TABLE_ENV + " is set to " + name + ", which is the table our cases "
            "live in. An institution that shares our state makes the trust "
            "boundary decorative -- give the desks their own table."
        )
    if _table is None:
        import boto3

        _table = boto3.resource("dynamodb").Table(name)
    return _table


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _time(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def _packed(ticket: Ticket) -> dict:
    return {
        "ref": ticket.ref,
        "case_id": ticket.case_id,
        "service": ticket.service,
        "body": ticket.body,
        "filed_at": _iso(ticket.filed_at),
        "responds_at": _iso(ticket.responds_at),
        "sla_deadline": _iso(ticket.sla_deadline),
        "will_breach": bool(ticket.will_breach),
        "will_false_close": bool(ticket.will_false_close),
        "status": ticket.status,
        "actually_resolved": bool(ticket.actually_resolved),
        "reason": ticket.reason or "",
    }


def _unpacked(row: dict) -> Ticket:
    return Ticket(
        ref=str(row.get("ref", "")),
        case_id=str(row.get("case_id", "")),
        service=str(row.get("service", "")),
        body=str(row.get("body", "")),
        filed_at=_time(row.get("filed_at")),
        responds_at=_time(row.get("responds_at")),
        sla_deadline=_time(row.get("sla_deadline")),
        will_breach=bool(row.get("will_breach")),
        will_false_close=bool(row.get("will_false_close")),
        status=str(row.get("status", "open")),
        actually_resolved=bool(row.get("actually_resolved")),
        reason=str(row.get("reason", "")),
    )


def load(desk: Desk) -> bool:
    """Fill this desk from its own table. True if anything was restored.

    Touches the private `_by_key` and `_n` deliberately: idempotency and the
    ticket numbering are part of the state a real office keeps, and restoring
    the tickets without them would hand the same complaint a second reference
    number on the next retry -- the duplicate hard rule 5 forbids.
    """
    table = _open()
    if table is None:
        return False
    item = table.get_item(Key={"desk": desk.profile.name}).get("Item")
    if not item:
        return False
    desk.tickets = {ref: _unpacked(row)
                    for ref, row in (item.get("tickets") or {}).items()}
    desk._by_key = {str(k): str(v) for k, v in (item.get("by_key") or {}).items()}
    desk._n = int(item.get("n") or 0)
    _restore_rng(desk, item.get("rng"))
    return True


def _restore_rng(desk: Desk, raw: Any) -> None:
    """Put the calibrated dice back where this desk left them.

    MEASURED, 14 Sep. Desk seeds `random.Random(profile.name)`, so every fresh
    instance replays one identical sequence. A laptop runs one long-lived
    process and the sequence advances across filings, which is what the
    calibrated rates describe. A microVM does not: without this, every cold
    start rewinds to roll one, and the deployed vendor and payments desks
    refused the first filing on a pretext every single time -- four probes,
    four identical refusals, a 0.24% event if it had really been chance.

    That would be our hosting quietly replacing the calibration with a fixed
    verdict, and the rate Kartik sweeps would stop meaning anything.

    A bad or absent value leaves the desk's own seeding alone rather than
    raising: a desk that has never been checkpointed is the ordinary first
    case, and a corrupt one should still answer.
    """
    if not raw:
        return
    try:
        version, internal, gauss = json.loads(raw)
        desk._rng.setstate((version, tuple(internal), gauss))
    except (TypeError, ValueError):
        # Left as seeded. Never fatal: the office still answers.
        return


def save(desk: Desk) -> bool:
    """Checkpoint this desk into its own table. True if anything was written.

    One item per desk. A whole-desk write rather than a row per ticket,
    because a desk's answer depends on the set (`_by_key`, the counter) and a
    half-written set is worse than a stale one. The 400 KB item ceiling is far
    away for a simulated ward: a ticket is a few hundred bytes.
    """
    table = _open()
    if table is None:
        return False
    table.put_item(Item={
        "desk": desk.profile.name,
        "tickets": {ref: _packed(t) for ref, t in desk.tickets.items()},
        "by_key": dict(desk._by_key),
        "n": desk._n,
        # The RNG POSITION is state too -- see _restore_rng. Stored as JSON
        # rather than as a DynamoDB list because getstate() is 625 ints and a
        # list of Decimals would be both larger and lossier on the way back.
        "rng": json.dumps(desk._rng.getstate()),
    })
    return True
