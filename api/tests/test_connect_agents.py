import json
from datetime import date

import anyio
import pytest
from mcp import Client
from starlette.testclient import TestClient

from neura1 import access, agent_mcp, brain, timeline
from neura1.config import settings
from neura1.connect import sync, zoho_sim
from neura1.graph import rows

EXPECTED = {
    ("stock", "VX7-MCU", "updated"), ("purchase_orders", "PO-2026-0131", "updated"), ("receipts", "GRN-26-0418", "new"),
    ("stock_moves", "SM-GRN-26-0418", "new"), ("tasks", "WRK-117", "updated"), ("tasks", "WRK-129", "updated"),
    ("tasks", "WRK-134", "new"),
}


def test_zoho_sync_brings_exactly_what_changed_in_zoho(fresh_graph):
    preview = sync.run(fresh_graph, dry_run=True, server=zoho_sim.mcp)
    assert preview["ok"] and preview["warnings"] == []
    assert {(c["kind"], c["id"], c["change"]) for c in preview["changes"]} == EXPECTED
    assert rows(fresh_graph, "MATCH (i:Item {id:'VX7-MCU'}) RETURN i.on_hand AS n")[0]["n"] == 320  # dry run wrote nothing
    po = next(c for c in preview["changes"] if c["id"] == "PO-2026-0131")
    assert po["fields"] == {"status": ["open", "received"]}

    done = sync.run(fresh_graph, server=zoho_sim.mcp, by="Praveen")
    assert done["ok"] and done["run"].startswith("SYNC-") and len(done["changes"]) == 7
    stock = rows(fresh_graph, "MATCH (i:Item {id:'VX7-MCU'}) RETURN i.on_hand AS n, i.allocated AS a")[0]
    assert stock == {"n": 520, "a": 40}  # Zoho's stock on hand; Neura1's allocation kept
    task = rows(fresh_graph, "MATCH (a:Action {id:'WRK-134'})-[:ASSIGNED_TO]->(p:Person), (a)-[:IN_PROJECT]->(pr:Project) "
                             "RETURN p.id AS who, pr.id AS project, a.due_date AS due")[0]
    assert task == {"who": "P-AMBIKA", "project": "PRJ-COSTDOWN", "due": "2026-11-06"}

    again = sync.run(fresh_graph, server=zoho_sim.mcp)
    assert again["changes"] == [] and "up to date" in again["message"]

    # The replan shows on the timeline against the original plan, and the sync is in What's new.
    t = timeline.timeline(fresh_graph, access.viewer(fresh_graph, "P-PRAVEEN"), date(2026, 10, 18))
    wrk = next(i for g in t["groups"] for i in g["items"] if i["id"] == "WRK-129")
    assert wrk["baseline"]["end"] == "2026-10-24" and wrk["plan"]["end"] == "2026-10-31" and wrk["deviation_days"] == 7
    feed = brain.changes(fresh_graph)["feed"]
    assert any(f["kind"] == "sync" and f["ref"] == "WRK-129" for f in feed)
    assert sync.history(fresh_graph)[0]["changes"] == 7


def test_zoho_dates_and_numbers_map_cleanly():
    assert sync._iso_mdy("10-31-2026") == "2026-10-31" and sync._iso_mdy("") == ""
    assert sync._norm("6.50") == sync._norm(6.5) == "6.5" and sync._norm(520.0) == sync._norm("520") == "520"
    assert sync._norm("2026-10-18") == "2026-10-18" and sync._norm("PO-2026-0131") == "PO-2026-0131"


def test_connect_reaches_the_source_over_stdio():
    probe = sync.probe()  # launches the simulated Zoho as a subprocess and speaks MCP to it
    assert probe["ok"], probe
    assert {t["name"] for t in probe["tools"]} == set(sync.TOOLS)


@pytest.fixture
def agent_graph(graph, monkeypatch):
    monkeypatch.setattr(agent_mcp, "get_graph", lambda: graph)
    monkeypatch.setattr(settings, "agent_viewer", None)
    return graph


def _call(tool: str, args: dict | None = None) -> dict:
    async def go():
        async with Client(agent_mcp.mcp) as c:
            r = await c.call_tool(tool, args or {})
            return json.loads("".join(getattr(x, "text", "") for x in r.content))
    return anyio.run(go)


def test_agents_get_read_only_tools_without_raw_cypher(agent_graph):
    async def go():
        async with Client(agent_mcp.mcp) as c:
            return {t.name for t in (await c.list_tools()).tools}
    names = anyio.run(go)
    assert {"change_impact", "timeline_deviations", "can_we_promise", "who_knows"} <= names
    assert not names & {"read_only_cypher", "propose_task"}


def test_an_external_agent_sees_no_amounts_and_no_leave(agent_graph):
    impact = _call("change_impact", {"item_id": "NB54360", "new_unit_price": 320, "lead_weeks": 22})
    cost = impact["result"]["cost"]
    assert impact["read_as"] == "External agent"
    assert cost["total_delta"] is None and cost["new_unit_price"] is None and cost["formula"] is None
    assert "320" not in json.dumps(impact["result"]["cost"])
    plan = _call("timeline_deviations")
    assert plan["read_as"] == "External agent" and plan["summary"]["late"] >= 1
    assert not any("away" in w for s in plan["slipping"] for w in s["why"])


def test_an_agent_reading_as_a_director_sees_what_they_see(agent_graph, monkeypatch):
    monkeypatch.setattr(settings, "agent_viewer", "P-PRAVEEN")
    impact = _call("change_impact", {"item_id": "NB54360", "new_unit_price": 320, "lead_weeks": 22})
    assert impact["read_as"] == "Praveen" and float(impact["result"]["cost"]["total_delta"]) == 37400


def test_employees_get_no_cost_figures_from_the_impact_api(graph, monkeypatch):
    from neura1 import main
    monkeypatch.setattr(main, "get_graph", lambda: graph)
    c = TestClient(main.app)
    c.app.dependency_overrides[main.graph] = lambda: graph
    try:
        r = c.post("/api/impact", json={"item": "NB54360", "new_unit_price": 320, "lead_weeks": 22},
                   headers={"x-neura1-as": "P-SAI"}).json()
    finally:
        c.app.dependency_overrides.clear()
    assert r["cost"]["total_delta"] is None and r["cost"]["formula"] is None and "money" in r["restricted"]


def test_the_agent_endpoint_is_off_without_a_token_and_checks_it(monkeypatch):
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    client = TestClient(agent_mcp.Gate(inner))
    monkeypatch.setattr(settings, "agent_mcp_token", None)
    assert client.post("/mcp").status_code == 404
    monkeypatch.setattr(settings, "agent_mcp_token", "s3cret-token")
    assert client.post("/mcp").status_code == 401
    assert client.post("/mcp", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/wrong/mcp").status_code == 401
    assert client.post("/mcp", headers={"Authorization": "Bearer s3cret-token"}).status_code == 200
    assert client.post("/s3cret-token/mcp").status_code == 200
    assert seen == ["/mcp", "/mcp"]  # the token never reaches the MCP app as part of the path
