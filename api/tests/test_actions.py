from datetime import date
from decimal import Decimal

from neura1.actions import approve, find_investigation
from neura1.graph import rows
from neura1.impact import ChangeEvent, analyse

NOTICE = "inbox/notice_NB54360_2026-10-14.md"


def test_approval_is_idempotent_and_survives_a_new_session(graph):
    report = analyse(graph, ChangeEvent("NB54360", Decimal(320), "INR", None, 22, date(2026, 10, 16), NOTICE))
    first = approve(graph, "NB54360", NOTICE, report["actions"], "demo reviewer", "37400", "INR",
                    {"cost_total": "37400"})
    assert len(first["created"]) == len(report["actions"]) and first["already_existed"] == []

    second = approve(graph, "NB54360", NOTICE, report["actions"], "demo reviewer", "37400", "INR")
    assert second["created"] == [] and len(second["already_existed"]) == len(report["actions"])
    assert rows(graph, "MATCH (:Investigation {id:$id})-[:PRODUCED]->(a:Action) RETURN count(a) AS n",
                {"id": first["investigation"]})[0]["n"] == len(report["actions"])

    # A fresh session only knows the item and the notice; it finds the earlier work.
    inv = find_investigation(graph, "NB54360", NOTICE)
    assert inv["id"] == first["investigation"]
    assert inv["snapshot"] == {"cost_total": "37400"}
    owners = {a["owner"] for a in inv["actions"]}
    assert {"Raghavendra", "Sai", "Satish", "Ambika"} <= owners
    cited = rows(graph, "MATCH (:Action)-[r:CITES]->(c:Chunk) RETURN count(r) AS n")[0]["n"]
    assert cited > 0


def test_task_from_a_draft_is_assigned_by_first_name_and_not_duplicated(fresh_graph):
    from neura1.actions import create_task

    first = create_task(fresh_graph, "Review pmic_seq.c for MX-3360", "Sai", "FW-PMIC-SEQ", "regulator change", "Hithesh")
    again = create_task(fresh_graph, "Review pmic_seq.c for MX-3360", "Sai", "FW-PMIC-SEQ", "regulator change", "Hithesh")
    assert first["new"] is True and first["owner"] == "Sai"
    assert again["new"] is False and again["id"] == first["id"]
    assert create_task(fresh_graph, "Something", "Nobody", None, "", "Hithesh")["owner"] is None


def test_moving_tasks_on_the_board_records_history(fresh_graph):
    from neura1.actions import board, create_task, set_status

    t = create_task(fresh_graph, "Requalify MX-3360", "Satish", "TP-PSM-07", "bench pass", "Hithesh")
    assert t["id"] in [x["id"] for x in board(fresh_graph)["columns"]["open"]]
    set_status(fresh_graph, t["id"], "in_progress", "Satish")
    set_status(fresh_graph, t["id"], "done", "Satish", "TR-140 passed")
    b = board(fresh_graph)
    done_before = len([x for x in board(fresh_graph)["columns"]["done"] if x["id"] != t["id"]])
    assert t["id"] in [x["id"] for x in b["columns"]["done"]] and b["pipeline"]["done"] == done_before + 1
    moves = fresh_graph.ro_query("MATCH (e:Event)-[:ON]->(:Action {id:$id}) RETURN e.from, e.to ORDER BY e.at",
                                 {"id": t["id"]}).result_set
    assert sorted(moves) == sorted([["open", "in_progress"], ["in_progress", "done"]])
    import pytest
    with pytest.raises(ValueError):
        set_status(fresh_graph, t["id"], "archived", "x")
