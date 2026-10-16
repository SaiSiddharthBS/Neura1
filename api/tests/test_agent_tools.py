"""Tool layer of the agent, tested without a model."""

import pytest

from neura1.agent import guard_cypher, run_tool
from neura1.impact import Trace


def test_cypher_guard_blocks_writes_and_adds_limit():
    with pytest.raises(ValueError):
        guard_cypher("MATCH (n) DETACH DELETE n")
    with pytest.raises(ValueError):
        guard_cypher("MATCH (n:Item) SET n.name = 'x' RETURN n")
    assert guard_cypher("MATCH (n:Item) RETURN n.id").endswith("LIMIT 50")


def test_who_knows_finds_owner_by_owned_id(graph):
    out = run_tool(graph, Trace(graph), "who_knows", {"text": "FW-PMIC-SEQ"})
    assert out["people"][0]["name"] == "Sai"


def test_propose_task_only_drafts_and_sources_are_collected(graph):
    from neura1.agent import _finish

    t = Trace(graph)
    draft = run_tool(graph, t, "propose_task", {"owner": "Sai", "title": "Review pmic_seq.c for MX-3360",
                                                  "target": "FW-PMIC-SEQ", "why": "regulator change"})
    profile = run_tool(graph, t, "person", {"name": "Sai"})
    out = _finish(graph, "Drafted a task for Sai.", [], t, [draft, profile])
    assert out["drafts"][0]["owner"] == "Sai"
    assert any(s.startswith("chats/") for s in out["sources"])
    assert graph.ro_query("MATCH (a:Action {kind:'task'}) RETURN count(a)").result_set[0][0] == 0


def test_read_only_cypher_runs_with_trace(graph):
    t = Trace(graph)
    out = run_tool(graph, t, "read_only_cypher", {"query": "MATCH (b:Build) RETURN b.id AS id ORDER BY id"})
    assert [r["id"] for r in out] == ["BO-0412", "BO-0415", "BO-0421"]
    assert t.steps[0]["cypher"].endswith("LIMIT 50")


def test_false_approval_claims_are_flagged(graph):
    from neura1.agent import check_approval_claims

    flagged = check_approval_claims(graph, "The only approved alternative is MX-3360. NB54361-L is not approved.")
    assert len(flagged) == 1 and "MX-3360" in flagged[0] and "NOT APPROVED" in flagged[0]
    assert check_approval_claims(graph, "MX-3360 is not approved yet.") == []


def test_resolve_item_handles_several_part_numbers_at_once(graph):
    out = run_tool(graph, Trace(graph), "resolve_item", {"text": "NB54360 NB54361-L"})
    assert {r["id"] for r in out} == {"NB54360", "NB54361-L"}


def test_incumbent_part_called_approved_is_not_flagged(graph):
    from neura1.agent import check_approval_claims

    assert check_approval_claims(graph, "The only approved part for this application is NB54360.") == []


def test_restricted_reader_gets_no_leave_dates_or_money_from_tools(graph):
    from neura1.agent import _restrict

    t = Trace(graph)
    away = run_tool(graph, t, "absence_impact", {"name": "Raghavendra"})
    hidden = _restrict("absence_impact", away, {"money": False, "leave_of": lambda _p: False})
    assert "absence" not in hidden and hidden["restricted"]
    cust = run_tool(graph, t, "customer", {"text": "Nilgiri"})
    assert _restrict("customer", cust, {"money": False, "leave_of": lambda _p: True})["open_value"] is None
