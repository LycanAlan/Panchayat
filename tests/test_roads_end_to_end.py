"""Potholes, end to end. The same spine as water, with nothing guessed.

A household types "pothole outside 14, 4th Cross" and picks Roads. From there
it is the water path with different curated data: routed to the BBMP ward
engineer with a citation, drafted, signed, filed against the ward desk AS A
ROADS COMPLAINT, tracked, and clustered with the neighbour who reports the same
hole. A street with no roads entry says so instead of inventing an office.

These go through the real doors -- run_request_path, digest.approve,
Watchdog.handle, the web Lambda -- and fake only two things: the clock, and the
A2A hop to the desk, which is answered by the real desk simulator in-process.

No AWS, no model.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import timedelta

import pytest

from agents import digest, pattern_watch, remedy
from agents.watchdog import Watchdog
from core import db, fakes
from core.clock import RealClock
from core.scoring import TAU, correlate
from core.types import CaseStatus, ConsentScope, Service
from graph.request_path import run_request_path
from handlers import temporal, web_api
from institutions.client import InstitutionClient, build_submit
from institutions.protocol import DeskReply
from institutions.routing import desk_for
from institutions.server import Desk, load_profile

STREET = "ward12-4thcross"
ROADS_FEEDER = "bbmp-rd-4thcross"

REPORT = {
    "household_id": "hh_roads", "member_id": "mem_roads", "name": "Ramesh",
    "role": "parent", "text": "pothole outside 14, 4th Cross, bikes falling",
    "language": "en", "segment": STREET, "service": "roads",
    "consent": ["join_collective"],
}


class RecordingClock:
    """Books wakes into a list. Time from the clock, never utcnow (rule 1)."""

    def __init__(self) -> None:
        self.t = RealClock().now()
        self.booked: list[tuple[str, str]] = []

    def now(self):
        return self.t

    def schedule(self, case_id: str, at, action: str) -> str:
        self.booked.append((case_id, action))
        return "handle-" + action

    def cancel(self, handle: str) -> None:
        pass


class WardDeskInProcess(InstitutionClient):
    """The real client, the real ward desk -- minus the network between them.

    Only `send()` is replaced. `file()` still enforces rule 4, desk_for() still
    picks the desk from the authority, and the desk simulator still decides
    whether it takes the service. Its random refusals and downtime are zeroed
    so the test is about routing, not luck.
    """

    def __init__(self) -> None:
        super().__init__()
        profile = dataclasses.replace(load_profile("ward"), unreachable_rate=0.0,
                                      reject_malformed_rate=0.0)
        self.desk = Desk(profile)
        self.sent: list[dict] = []

    def send(self, desk: str, instruction: str) -> DeskReply:
        payload = json.loads(instruction.rsplit("\n\n", 1)[1])
        self.sent.append({"desk": desk, **payload})
        assert desk == "ward", "a roads tier went to " + desk
        return self.desk.accept(payload["case_id"], payload["service"],
                                payload["body"], payload["idempotency_key"])


# -------------------------------------------------------------- the data


def test_a_roads_entry_exists_with_a_cited_ladder():
    entry = remedy.lookup("roads", STREET)
    assert entry is not None
    assert entry.authority == "BBMP"
    assert "BWSSB" in entry.not_authority
    assert entry.feeder_id == ROADS_FEEDER
    assert entry.required_fields == ["location", "duration_days", "affected_count"]
    assert [s.tier for s in entry.ladder] == [1, 2, 3, 4]
    for step in entry.ladder:
        assert step.statute_ref and step.window_days > 0, step.tier


def test_the_roads_ladder_climbs_through_the_ward_desk_and_stops_at_rti():
    entry = remedy.lookup("roads", STREET)
    desks = [desk_for(step.authority) for step in entry.ladder]
    assert [d.desk for d in desks[:3]] == ["ward", "ward", "ward"]
    assert not desks[3].is_filable, "an RTI must never be filed by the system"


def test_the_water_entry_on_the_same_street_is_untouched():
    entry = remedy.lookup("water", STREET)
    assert entry.authority == "BWSSB"
    assert entry.feeder_id == "bwssb-tm-14"


@pytest.mark.parametrize("segment", ["ward12-stationroad", "ward12-5thcross",
                                     "ward12-oldvillage"])
def test_a_street_without_a_roads_entry_is_not_guessed(segment):
    assert remedy.lookup("roads", segment) is None


def test_a_roads_letter_reads_as_a_roads_letter():
    """No RR number, and no 'days without supply' in a pothole complaint."""
    entry = remedy.lookup("roads", STREET)
    case = fakes.a_case(service=Service.ROADS, segment=STREET,
                        feeder_id=ROADS_FEEDER, authority="BBMP")
    body, missing = remedy.compose_filing(case, entry, {
        "location": "outside 12/14", "duration_days": 9, "affected_count": 3})
    assert missing == []
    assert body.startswith("Roads complaint")
    assert "Days the defect has stood: 9." in body
    assert "RR number" not in body and "without supply" not in body

    water = remedy.lookup("water", STREET)
    water_body, _ = remedy.compose_filing(fakes.a_case(), water, {
        "rr_number": "RR-1", "duration_days": 3, "affected_count": 2})
    assert "Days without supply: 3." in water_body


def test_the_ward_desk_takes_a_roads_filing_and_issues_a_ward_ticket():
    client = WardDeskInProcess()
    reply = client.file_for_authority(
        authority="BBMP Assistant Engineer, ward office (roads)",
        case_id="case_r1", service="roads",
        body="Roads complaint. Duration 9 days. Households affected: 3.",
        idempotency_key="idem-roads-1", signed_by="mem_roads")
    assert reply.filed
    assert reply.ref.startswith("WARD-")


# ---------------------------------------------------------- the request path


def test_a_roads_report_routes_to_the_ward_engineer_with_a_citation():
    out = run_request_path(dict(REPORT))

    assert out["authority"] == "BBMP"
    assert "s.211(1)" in out["citation"]
    assert out["filed_to"] == "BBMP Assistant Engineer, ward office (roads)"
    assert out["unrouted_reason"] is None
    routed = [t for t in out["trace"]["transitions"] if t["status"] == "ROUTED"]
    assert routed and "not BWSSB" in routed[0]["detail"]

    case = db.get_case(out["case_id"])
    assert case.service is Service.ROADS
    assert case.feeder_id == ROADS_FEEDER
    assert db.get_claim(out["claim_id"]).feeder_id == ROADS_FEEDER


def test_report_sign_file_track():
    """The whole gate: report -> sign -> Watchdog -> ward ticket -> TRACKING,
    through the composition the temporal Lambda uses, so the desk is told the
    case is roads rather than the water default."""
    out = run_request_path(dict(REPORT))
    case_id = out["case_id"]
    (pending,) = db.unsigned_filings(case_id)

    clock = RecordingClock()
    signed, _ = digest.approve(pending.idempotency_key, "mem_roads", clock)
    assert signed

    client = WardDeskInProcess()
    submit = build_submit(client=client, service_of=temporal._service_of)
    clock.t += timedelta(minutes=2)
    Watchdog(submit=submit).handle(case_id, "retry_submit", clock)

    (sent,) = client.sent
    assert sent["service"] == "roads"
    assert sent["case_id"] == case_id
    case = db.get_case(case_id)
    assert case.status is CaseStatus.TRACKING
    assert db.get_filing(pending.idempotency_key).external_ref.startswith("WARD-")


def test_the_lambda_would_file_a_water_case_as_water():
    """Same composition, other service: nothing regressed for water."""
    water = run_request_path({**REPORT, "household_id": "hh_water",
                              "service": "water", "text": "no water for three days"})
    roads = run_request_path(dict(REPORT))
    assert temporal._service_of(water["case_id"]) == "water"
    assert temporal._service_of(roads["case_id"]) == "roads"


def test_a_missing_case_is_an_error_not_a_water_default():
    with pytest.raises(LookupError):
        temporal._service_of("case_does_not_exist")


# --------------------------------------------------------------- the door


def test_the_door_turns_an_uncurated_roads_street_into_a_409(monkeypatch):
    """The runtime's own answer for a street with no roads entry, through the
    real request path, mapped by the real door."""
    monkeypatch.setenv("PANCHAYAT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:ap-south-2:1:runtime/x")
    monkeypatch.setattr(web_api, "_invoke",
                        lambda payload, session_id: {"result": run_request_path(payload)})

    resp = web_api.handler({
        "rawPath": "/api", "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps({**REPORT, "action": "report",
                            "segment": "ward12-stationroad"}),
    })

    assert resp["statusCode"] == 409
    body = json.loads(resp["body"])
    assert body["error"] == "not_routable_here"
    assert "no curated roads authority" in body["message"]


# ------------------------------------------------------------ the street


def _roads_claim(**kw):
    d = dict(household_id=fakes.new_id("hh"), service=Service.ROADS,
             segment=STREET, feeder_id=ROADS_FEEDER,
             description="Pothole on the carriageway outside 12/14",
             consent_scopes=[ConsentScope.FILE_INDIVIDUAL, ConsentScope.JOIN_COLLECTIVE])
    d.update(kw)
    return fakes.a_claim(**d)


class FixedClock:
    def __init__(self, now):
        self._now = now

    def now(self):
        return self._now

    def schedule(self, case_id, at, action) -> str:
        return "handle"

    def cancel(self, handle) -> None:
        pass


def test_two_households_reporting_one_hole_become_one_case():
    """Anti-Abuse and Pattern Watch take a bbmp-rd-* feeder exactly as they
    take a trunk main: one fault on one street is one case."""
    claims = [_roads_claim(created_at=fakes.T0 + timedelta(hours=i * 3),
                           observed_since=fakes.T0 - timedelta(days=3))
              for i in range(2)]
    cases = []
    for i, claim in enumerate(claims):
        case = fakes.a_case(service=Service.ROADS, feeder_id=ROADS_FEEDER,
                            authority="BBMP", status=CaseStatus.DRAFTED,
                            created_at=fakes.T0 + timedelta(minutes=i),
                            claim_ids=[claim.claim_id],
                            household_ids=[claim.household_id], merged_from=[])
        db.put_claim(claim)
        db.put_case(case)
        cases.append(case)
    survivor, source = cases

    watch = pattern_watch.PatternWatch(clock=FixedClock(fakes.T0 + timedelta(hours=36)))
    proposal = watch.on_new_claim(claims[1])
    assert proposal is not None, "two reports of one hole did not cross TAU"
    gated = watch.gate.verify(proposal, case=survivor, claims=claims)
    assert watch.apply_upgrade(gated) == survivor.case_id

    kept = db.get_case(survivor.case_id)
    assert kept.corroboration == 2
    assert db.get_case(source.case_id).status is CaseStatus.WITHDRAWN


def test_a_hole_on_the_next_street_does_not_corroborate():
    """5th Cross is next door and has no roads entry, so its claim carries no
    feeder. Adjacency alone scores 0.15 on topology -- nowhere near TAU."""
    here = _roads_claim(created_at=fakes.T0)
    next_street = _roads_claim(segment="ward12-5thcross", feeder_id="",
                               created_at=fakes.T0 + timedelta(hours=1))
    score = correlate(here, next_street)
    assert score.topology == 0.15
    assert not score.above_threshold and score.total < TAU


def test_a_water_report_on_the_same_street_never_joins_the_pothole():
    pothole = _roads_claim(created_at=fakes.T0)
    dry_tap = fakes.a_claim(segment=STREET, created_at=fakes.T0 + timedelta(minutes=5))
    assert not correlate(pothole, dry_tap).above_threshold
