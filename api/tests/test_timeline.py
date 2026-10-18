from datetime import date

from neura1 import access, promise, timeline
from neura1.ingest.structured import load_rows

TODAY = date(2026, 10, 18)


def _items(t):
    return {i["id"]: i for g in t["groups"] for i in g["items"]}


def test_build_and_order_forecasts_follow_the_supplier_notice(graph):
    t = timeline.timeline(graph, access.viewer(graph, "P-PRAVEEN"), TODAY)
    items = _items(t)
    bo = items["BO-0412"]
    assert bo["plan"] == {"start": "2026-11-03", "end": "2026-11-20"}
    assert bo["forecast"]["start"] == "2027-03-21"  # 22 weeks from today, by the NB54360 notice
    assert bo["driver"] == "NB54360" and bo["state"] == "late"
    assert "short 240 of 300" in bo["reasons"][0]
    so = items["SO-881"]
    assert so["forecast"]["end"] == "2027-04-11" and so["deviation_days"] == 142
    # The same date "Can we promise" gives: parts arrive, then three weeks to ship.
    p = promise.check(graph, "PDU-28-C", 80, date(2026, 11, 20), access.viewer(graph, "P-PRAVEEN"), today=TODAY)
    assert p["earliest"] == so["forecast"]["end"]


def test_project_finishes_with_its_latest_item(graph):
    t = timeline.timeline(graph, access.viewer(graph, "P-PRAVEEN"), TODAY)
    nilgiri = next(g for g in t["groups"] if g["id"] == "PRJ-NILGIRI")
    assert nilgiri["forecast"]["end"] == "2027-04-11" and nilgiri["deviation_days"] == 117
    assert nilgiri["driver"] in ("BO-0412", "SO-881") and nilgiri["state"] == "late"
    as9100 = next(g for g in t["groups"] if g["id"] == "PRJ-AS9100")
    assert as9100["deviation_days"] == 0


def test_tasks_overdue_done_late_and_leave(graph):
    items = _items(timeline.timeline(graph, access.viewer(graph, "P-PRAVEEN"), TODAY))
    assert items["WRK-124"]["state"] == "late" and items["WRK-124"]["forecast"]["end"] == "2026-10-18"
    assert items["WRK-101"]["state"] == "done_late" and items["WRK-101"]["deviation_days"] == 4
    assert items["WRK-106"]["state"] == "done"  # finished early
    # Raghavendra is away 2 to 27 November: every working day of that leave pushes the thermal model out.
    assert items["WRK-102"]["forecast"]["end"] == "2026-12-11" and items["WRK-102"]["deviation_days"] == 28
    assert any("Raghavendra is away" in r for r in items["WRK-102"]["reasons"])
    # Work on a late build is flagged even when its own dates hold.
    assert items["WRK-121"]["state"] == "at_risk" and items["WRK-121"]["driver"] == "BO-0412"
    assert items["WRK-122"]["driver"] is None  # finished work is not held up by anything


def test_leave_is_only_weighed_for_readers_allowed_to_see_it(graph):
    t = timeline.timeline(graph, access.viewer(graph, "P-SAI"), TODAY)
    items = _items(t)
    assert t["leave_included"] is False
    assert items["WRK-102"]["deviation_days"] == 0
    assert not any("away" in r for i in items.values() for r in i["reasons"] if i["owner"] != "Sai")
    assert "penalty" not in items["SO-881"]  # money stays with directors and leadership
    leader = _items(timeline.timeline(graph, access.viewer(graph, "P-PRAVEEN"), TODAY))
    assert leader["SO-881"]["penalty"]["pct"] == 5.0


def test_a_replan_keeps_the_baseline(fresh_graph):
    row = {"id": "WRK-129", "title": "Vindhya Rail tender response", "assignee_id": "P-KEERTHANA", "project_id": "",
           "target_id": "C-VINDHYA", "status": "in_progress", "created": "2026-10-03", "completed": "",
           "start": "2026-10-03", "due": "2026-10-31"}
    load_rows(fresh_graph, "tasks", [row], "import/tasks.csv")
    item = _items(timeline.timeline(fresh_graph, access.viewer(fresh_graph, "P-PRAVEEN"), TODAY))["WRK-129"]
    assert item["baseline"]["end"] == "2026-10-24" and item["plan"]["end"] == "2026-10-31"
    assert item["deviation_days"] == 7 and item["state"] == "late"
    assert any(r.startswith("Replanned: due 2026-10-31, originally 2026-10-24") for r in item["reasons"])


def test_working_days():
    assert timeline.workdays(date(2026, 10, 19), date(2026, 10, 25)) == 5
    assert timeline.add_workdays(date(2026, 10, 23), 1) == date(2026, 10, 26)
