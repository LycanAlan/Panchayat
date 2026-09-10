"""The A2A client. Runs offline, with no desk listening.

Owner: Alakshendra
"""

from institutions.client import InstitutionClient, build_filing_tool
from institutions.protocol import DeskReply, Outcome


def test_endpoint_comes_from_the_profile_port():
    # The profile is the single source of truth for where a desk listens, so
    # changing a port in one YAML cannot leave the client pointing elsewhere.
    assert InstitutionClient().endpoint_for("bwssb").endswith(":9002")
    assert InstitutionClient().endpoint_for("ward").endswith(":9001")


def test_an_explicit_endpoint_wins():
    client = InstitutionClient(endpoints={"bwssb": "http://elsewhere:1234"})
    assert client.endpoint_for("bwssb") == "http://elsewhere:1234"


def test_env_overrides_the_default(monkeypatch):
    monkeypatch.setenv("WATER_ENDPOINT", "http://staging:9999")
    assert InstitutionClient().endpoint_for("bwssb") == "http://staging:9999"


def test_no_desk_listening_is_unreachable_not_an_exception():
    # This is the whole offline story. Nothing is running on this port, and the
    # caller still gets a reply it can act on: pause the clock and retry.
    client = InstitutionClient(endpoints={"bwssb": "http://localhost:9"}, timeout=1)
    reply = client.file("bwssb", "case_1", "water", "duration 3 days, affected 9", "idem-1")
    assert reply.outcome is Outcome.UNREACHABLE
    assert reply.should_pause_sla


def test_an_unfilable_authority_needs_a_human_rather_than_a_resubmission():
    # Tier 4. The system drafts an RTI and refuses to file it, and the reason
    # is what the Digest puts in front of a human. Distinct from REJECTED so
    # the Watchdog does not sit there resubmitting something no desk accepts.
    reply = InstitutionClient().file_for_authority(
        authority="RTI application (drafted only, never filed by the system)",
        case_id="case_1", service="water", body="...", idempotency_key="idem-2",
    )
    assert reply.outcome is Outcome.NEEDS_HUMAN
    assert reply.needs_human and not reply.should_retry
    assert "Rs 10" in reply.detail or "fee" in reply.detail


def test_a_desk_that_answers_nonsense_pauses_the_clock():
    # A live desk whose model fails returns prose like "Agent execution failed".
    # Nothing landed, so it must not read as UNKNOWN -- UNKNOWN does not pause
    # the SLA, and the statutory window would burn against a filing never made.
    class Broken(InstitutionClient):
        def _agent(self, desk):
            class Stub:
                def __call__(self, _instruction):
                    class R:
                        message = "Agent execution failed"
                    return R()
            return Stub()

    reply = Broken().file("bwssb", "case_1", "water", "body", "idem-9")
    assert reply.outcome is Outcome.UNREACHABLE
    assert reply.should_pause_sla


def test_an_agent_message_is_read_as_text_not_as_a_repr():
    # Regression, and the worst of the batch. str() on a Strands message yields
    # a Python repr, whose trailing "'}]}" ended up inside the ticket reference
    # -- so a filing that genuinely landed became unreachable by ref forever.
    class Result:
        def __init__(self):
            self.message = {"role": "assistant",
                            "content": [{"text": "ACCEPTED BWSSB-100001: sla_days=7"}]}

    text = InstitutionClient._text_of(Result())
    reply = DeskReply.find(text)
    assert reply.ref == "BWSSB-100001"


def test_the_filing_tool_is_well_formed_for_a_graph_node():
    # Ali drops this straight into tools=[...]. If the spec is wrong the model
    # calls it with the wrong arguments and the failure looks like a bad filing.
    client = InstitutionClient(endpoints={"bwssb": "http://localhost:9"}, timeout=1)
    tool = build_filing_tool(client)

    assert tool.tool_name == "file_with_authority"
    params = tool.tool_spec["inputSchema"]["json"]["properties"]
    assert set(params) == {"authority", "case_id", "service", "body",
                           "idempotency_key"}


def test_the_tool_and_the_client_agree_on_the_wire_grammar():
    # The tool is a thin render() over the client, so what a graph node gets
    # back has to parse with the same vocabulary the desk rendered with.
    client = InstitutionClient(endpoints={"bwssb": "http://localhost:9"}, timeout=1)
    reply = client.file_for_authority(
        authority="BWSSB Assistant Engineer, sub-division office",
        case_id="case_1", service="water", body="duration 3 days, affected 9",
        idempotency_key="idem-3",
    )
    assert DeskReply.parse(reply.render()) == reply
    assert reply.outcome is Outcome.UNREACHABLE
