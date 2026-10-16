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
    assert rows(graph, "MATCH (a:Action) RETURN count(a) AS n")[0]["n"] == len(report["actions"])

    # A fresh session only knows the item and the notice; it finds the earlier work.
    inv = find_investigation(graph, "NB54360", NOTICE)
    assert inv["id"] == first["investigation"]
    assert inv["snapshot"] == {"cost_total": "37400"}
    owners = {a["owner"] for a in inv["actions"]}
    assert {"Priya Nair", "Rahul Iyer", "Ananya Rao", "Meera Kulkarni"} <= owners
    cited = rows(graph, "MATCH (:Action)-[r:CITES]->(c:Chunk) RETURN count(r) AS n")[0]["n"]
    assert cited > 0
