"""Company events beyond supplier changes, on the fixture."""

from datetime import date

from neura1 import scenarios as S
from neura1.actions import approve, board


def test_absence_plan_follows_the_handover_policy(fresh_graph):
    r = S.absence_impact(fresh_graph, "P-PRIYA")
    assert r["absence"] == {"start": "2026-11-02", "end": "2026-11-27"}
    assert r["person"]["backup"] == "Arjun Mehta" and r["person"]["manager"] == "Arjun Mehta"
    kinds = {a["kind"] for a in r["actions"]}
    assert {"interim_owner", "confirm_handover"} <= kinds
    assert any(a["id"] == "PSU-24" for a in r["knowledge_at_risk"])


def test_escalation_plan_crosses_departments_and_lands_on_the_board(fresh_graph):
    c = S.customer_360(fresh_graph, "C-DECCAN")
    assert c["rank"] == 2 and c["escalation"].startswith("inbox/escalation_")
    owners = {a["owner"] for a in c["actions"]}
    assert {"Farhan Sheikh", "Sanjay Pillai", "Rahul Iyer", "Vikram Desai", "Kavya Menon"} <= owners
    approve(fresh_graph, "C-DECCAN", c["escalation"], c["actions"], "Kavya Menon", None, None, kind="escalation")
    tasks = board(fresh_graph)["columns"]["open"]
    assert len(tasks) == len(c["actions"]) and {t["plan_kind"] for t in tasks} == {"escalation"}


def test_risk_radar_finds_the_single_sourced_part_and_cross_team_cluster(fresh_graph):
    r = S.risk_radar(fresh_graph, date(2026, 10, 16))
    assert [x["id"] for x in r["single_source"]] == ["NB54360"]
    assert r["single_source"][0]["value_at_risk"] == 3360000 + 1920000 + 1680000
    assert any(set(c["people"]) == {"Rahul Iyer", "Sanjay Pillai"} and c["crosses_teams"] for c in r["communities"])
    assert r["chokepoints"] and r["chokepoints"][0]["score"] > 0


def test_signals_route_to_the_right_subject(fresh_graph):
    kinds = {s["kind"]: s["subject"] for s in S.signals(fresh_graph)}
    assert kinds == {"notice": "NB54360", "escalation": "C-DECCAN", "leave": "P-PRIYA"}
