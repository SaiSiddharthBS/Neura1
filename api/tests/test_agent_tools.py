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


def test_who_finds_owner_by_owned_id(graph):
    out = run_tool(graph, Trace(graph), "who", {"text": "FW-PMIC-SEQ"})
    assert [r["name"] for r in out] == ["Rahul Iyer"]


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
