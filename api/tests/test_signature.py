"""Signature features: the company sandbox, "Can we promise this?" and knowledge rescue."""

from datetime import date

from neura1 import promise, rescue, sandbox
from neura1.access import viewer
from neura1.ingest import extract

TODAY = date(2026, 10, 17)


def test_sandbox_runs_on_a_copy_and_finds_what_only_the_combination_shows(fresh_graph):
    extract.load_snapshots(fresh_graph)
    before = fresh_graph.query("MATCH (a:Absence) RETURN count(a)").result_set[0][0]
    r = sandbox.run(fresh_graph, sandbox.PRESETS[0]["shocks"], TODAY)
    assert fresh_graph.query("MATCH (a:Absence) RETURN count(a)").result_set[0][0] == before  # never written
    assert r["metrics"]["builds_at_risk"] == 3 and r["metrics"]["orders_exposed"] == 3
    combined = [f for f in r["findings"] if f["only_in_combination"]]
    # The regulator change needs Sai's firmware review, and Sai is away in the same weeks.
    assert any("pmic_seq.c" in f["title"] and "Sai" in f["detail"] for f in combined)
    assert r["copies"] == 4 and r["copy_ms"] < 2000


def test_sandbox_rejects_unknown_changes(fresh_graph):
    import pytest
    with pytest.raises(sandbox.SandboxError):
        sandbox.run(fresh_graph, [{"kind": "part", "item": "NOPE-1", "eol": True}], TODAY)
    with pytest.raises(sandbox.SandboxError):
        sandbox.run(fresh_graph, [], TODAY)


def test_a_promise_uses_the_newest_lead_time_not_the_quote(fresh_graph):
    extract.load_snapshots(fresh_graph)
    lead = viewer(fresh_graph, "P-HITHESH")
    r = promise.check(fresh_graph, "PDU-28", 50, date(2026, 12, 31), lead, TODAY)
    assert r["verdict"] == "no" and r["limiting"] == "NB54360"
    assert r["stock_and_quote_says"]["verdict"] == "yes"  # the quote alone would have said yes
    nb = next(c for c in r["constraints"] if c["subject"] == "NB54360")
    assert nb["lead"]["basis"] == "notice" and nb["lead"]["weeks"] == 22
    assert any("NB54361-L" in f and "rejected" in f for f in r["fixes"])
    assert any(c["kind"] == "people" and c["subject"] == "Raghavendra" for c in r["constraints"])


def test_a_promise_hides_leave_from_people_who_may_not_see_it(fresh_graph):
    extract.load_snapshots(fresh_graph)
    r = promise.check(fresh_graph, "PDU-28", 50, date(2026, 12, 31), viewer(fresh_graph, "P-KEERTHANA"), TODAY)
    assert not any(c["kind"] == "people" for c in r["constraints"]) and not r["leave_included"]
    assert r["purchase_value"] is None  # no amounts either
    assert promise.check(fresh_graph, "PDU-28 Rev B", 5, date(2027, 1, 10), viewer(fresh_graph, "P-HITHESH"),
                         TODAY)["verdict"] == "no"


def test_knowledge_rescue_turns_answers_into_linked_knowledge(fresh_graph):
    plan = rescue.plan(fresh_graph, "P-SAI")
    q = next(x for x in plan["questions"] if x["id"] == "dep:FW-PMIC-SEQ")
    assert "NB54360" in q["question"]
    saved = rescue.save(fresh_graph, "P-SAI", q["id"], q["question"], q["about"],
                        "The power-good wait in pmic_seq.c is 6 ms since FW-233. Vinay knows the bench rig.", None)
    assert {"FW-PMIC-SEQ", "NB54360"} <= set(saved["about"])
    again = rescue.plan(fresh_graph, "P-SAI")
    assert next(x for x in again["questions"] if x["id"] == q["id"])["answered"]
    assert rescue.coverage(fresh_graph, "P-SAI")["FW-PMIC-SEQ"] == 1
    hits = fresh_graph.query("CALL db.idx.fulltext.queryNodes('Chunk', 'bench rig') YIELD node RETURN node.id").result_set
    assert any(h[0] == saved["id"] for h in hits)  # searchable company knowledge


def test_the_agent_tool_drops_leave_for_readers_who_may_not_see_it(fresh_graph):
    from neura1.agent import _restrict
    extract.load_snapshots(fresh_graph)
    r = promise.check(fresh_graph, "PDU-28", 50, date(2026, 12, 31), viewer(fresh_graph, "P-HITHESH"), TODAY)
    assert any(c["kind"] == "people" for c in r["constraints"])
    shown = _restrict("can_we_promise", r, {"money": False, "leave_of": lambda _p: False})
    assert not any(c["kind"] == "people" for c in shown["constraints"])
