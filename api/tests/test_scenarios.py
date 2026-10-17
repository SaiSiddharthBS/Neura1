"""Company events beyond supplier changes, on the fixture."""

from datetime import date

from neura1 import scenarios as S
from neura1.actions import approve, board


def test_absence_plan_follows_the_handover_policy(fresh_graph):
    r = S.absence_impact(fresh_graph, "P-RAGHAVENDRA")
    assert r["absence"] == {"start": "2026-11-02", "end": "2026-11-27"}
    assert r["person"]["backup"] == "Vishwas" and r["person"]["manager"] is None  # no line managers below leadership
    kinds = {a["kind"] for a in r["actions"]}
    assert {"interim_owner", "confirm_handover"} <= kinds
    confirm = next(a for a in r["actions"] if a["kind"] == "confirm_handover")
    assert confirm["owner"] is None and "leadership team" in confirm["why"]  # left for leadership to pick up
    assert any(a["id"] == "PSM-28" for a in r["knowledge_at_risk"])


def test_escalation_plan_crosses_departments_and_lands_on_the_board(fresh_graph):
    c = S.customer_360(fresh_graph, "C-KONKAN")
    assert c["rank"] == 2 and c["escalation"].startswith("inbox/escalation_")
    owners = {a["owner"] for a in c["actions"]}
    assert {"Keerthana", "Nagarjun", "Sai", "Sharath", "Suresh"} <= owners
    approve(fresh_graph, "C-KONKAN", c["escalation"], c["actions"], "Hithesh", None, None, kind="escalation")
    tasks = [t for t in board(fresh_graph)["columns"]["open"] if t["plan_kind"] == "escalation" and t["investigation"]]
    assert len(tasks) == len(c["actions"])


def test_risk_radar_finds_the_single_sourced_part_and_work_clusters(fresh_graph):
    r = S.risk_radar(fresh_graph, date(2026, 10, 16))
    assert [x["id"] for x in r["single_source"]] == ["NB54360"]
    assert r["single_source"][0]["value_at_risk"] == 3360000 + 1920000 + 1680000
    assert any(len(c["people"]) >= 2 and c["records"] for c in r["communities"])
    assert r["chokepoints"] and r["chokepoints"][0]["score"] > 0


def test_signals_route_to_the_right_subject(fresh_graph):
    kinds = {s["kind"]: s["subject"] for s in S.signals(fresh_graph)}
    assert kinds == {"notice": "NB54360", "escalation": "C-KONKAN", "leave": "P-RAGHAVENDRA"}
