"""The deploy IAM policy, checked against the code it is supposed to permit.

WHY THIS FILE EXISTS. A policy document is the one artefact in this repo that
nothing executes before Thursday. `docs/deploy/runtime-table-policy.json`
scoped the scheduler permissions to `schedule/default/panchayat-*`, and
`core/clock.py` names every schedule `pnc-<case_id>-<action>`. Both were
written carefully; neither was written next to the other. The result is an
AccessDenied on the first `create_schedule` a real deploy attempts -- so the
case gets no wake, `_check_sla` never runs, and the eleven-week pursuit that
is the whole product is silently absent in the only environment that counts.

Nothing else in the suite touches this file, and no amount of `pytest` on a
laptop would have found it. These tests are cheap and they run offline.

Owner: Kartik (found while verifying the deploy path; the policy is Ali's)
"""
from __future__ import annotations

import json
import pathlib

from core.clock import SCHEDULE_PREFIX

_POLICY = (pathlib.Path(__file__).resolve().parents[1]
           / "docs" / "deploy" / "runtime-table-policy.json")


def _statements() -> list[dict]:
    doc = json.loads(_POLICY.read_text(encoding="utf-8"))
    body = doc["Statement"]
    return body if isinstance(body, list) else [body]


def _resources(statement: dict) -> list[str]:
    res = statement.get("Resource", [])
    return res if isinstance(res, list) else [res]


def test_the_policy_is_valid_json_with_statements():
    # It is deployed by copy-paste into the console. A trailing comma here is
    # not a style problem, it is a deploy that does not happen.
    assert _statements(), "the policy has no statements"


def test_the_scheduler_arn_matches_the_names_the_code_actually_creates():
    """THE BUG THIS FILE WAS WRITTEN FOR.

    `VirtualClock`/`RealClock.schedule()` builds `pnc-<case>-<action>`. If the
    policy's resource glob does not cover that prefix, every wake this system
    tries to book is refused -- and refused at deploy time, where nobody is
    watching a pytest run.
    """
    scheduler = [s for s in _statements()
                 if any("scheduler" in str(a)
                        for a in _actions(s))]
    assert scheduler, "nothing in the policy permits EventBridge Scheduler"

    globs = [r for s in scheduler for r in _resources(s)
             if ":scheduler:" in r]
    assert globs, "the scheduler statement names no schedule ARN"

    sample = SCHEDULE_PREFIX + "case_ab3f0011" + "-check_sla"
    assert any(_matches(g, sample) for g in globs), (
        "no resource in the policy covers a schedule named " + sample
        + " -- the ARNs are " + repr(globs))


def test_passrole_is_confined_to_the_scheduler_service():
    """A wildcard PassRole is the classic privilege-escalation shape, and this
    role is handed to EventBridge on every schedule creation."""
    for s in _statements():
        if "iam:PassRole" not in _actions(s):
            continue
        assert "*" not in _resources(s), "PassRole on a wildcard resource"
        condition = s.get("Condition", {}).get("StringEquals", {})
        assert condition.get("iam:PassedToService") == "scheduler.amazonaws.com"
        return
    raise AssertionError("the policy never grants iam:PassRole, so the "
                         "Runtime cannot hand EventBridge its invoke role")


# ------------------------------------------------------------------ helpers

def _actions(statement: dict) -> list[str]:
    act = statement.get("Action", [])
    return act if isinstance(act, list) else [act]


def _matches(glob: str, name: str) -> bool:
    """Does this ARN glob cover a schedule with that name?

    Only the trailing `*` form IAM actually uses here; a full ARN matcher
    would be more code than the thing it is checking.
    """
    tail = glob.rsplit("/", 1)[-1]
    return name.startswith(tail[:-1]) if tail.endswith("*") else tail == name
