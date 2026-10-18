from datetime import date

from neura1 import departments
from neura1.graph import rows

TODAY = date(2026, 10, 18)


def test_each_department_agent_finds_real_work_and_reports_it(fresh_graph):
    got = {a["id"]: departments.run(fresh_graph, a["id"], TODAY) for a in departments.AGENTS}
    assert got["procurement"]["findings"][0]["ref"] == "NB54360"
    assert {f["ref"] for f in got["production"]["findings"]} == {"BO-0412", "BO-0415", "BO-0421"}
    assert {f["ref"] for f in got["sales"]["findings"]} == {"SO-881", "SO-884", "SO-887"}
    assert any("Buying guide" in f["text"] for f in got["engineering"]["findings"])
    assert all(r["posted"] for r in got.values())
    posted = rows(fresh_graph, "MATCH (c:Chunk)-[:PART_OF]->(:Source {id:'chat/production'}) RETURN c.text AS t")
    assert any("Production agent" in p["t"] for p in posted)
    # #general is read by everyone: no penalty or amounts there
    general = rows(fresh_graph, "MATCH (c:Chunk)-[:PART_OF]->(:Source {id:'chat/general'}) RETURN c.text AS t")
    assert not any("enalty" in p["t"] or "₹" in p["t"] for p in general if "Sales agent" in p["t"])


def test_a_second_pass_reports_only_what_is_new(fresh_graph):
    departments.run(fresh_graph, "production", TODAY)
    again = departments.run(fresh_graph, "production", TODAY)
    assert again["new"] == [] and len(again["findings"]) == 3
    assert [s["last"]["findings"] for s in departments.status(fresh_graph) if s["id"] == "production"] == [3]
