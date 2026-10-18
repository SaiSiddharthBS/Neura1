"""Department agents: one always-ready agent per department, each in its own harness.

A harness is what keeps an agent useful and safe: a standing goal, the few Neura1 engines it may use, the channel
where it reports, and the reader it reads as (an agent sees what the department lead would see, no more). Every check
is done by code over the graph, so a finding is never invented; the agent's job is to look every time, notice what
changed, and say it in the department's channel with links to the evidence.

  procurement  → #supply       parts running short, orders due, supplier notices
  production   → #production   builds that cannot start on time, and why
  engineering  → #engineering  living documents that disagree with the graph
  sales        → #general      customer orders that will ship late, and penalty exposure for leadership

Agents run when someone presses Run (or all together), and can be scheduled. They only read and post: tasks and
purchase orders stay a human approval.
"""

from datetime import date, datetime, timezone

from falkordb import Graph

from neura1 import access
from neura1.graph import rows

AGENTS = [
    {"id": "procurement", "name": "Procurement agent", "channel": "supply", "reads_as": "P-PRAVEEN",
     "goal": "Keep every planned build supplied: flag parts that run short, orders that must go out now, and supplier notices.",
     "tools": ["inventory", "supplier notices", "purchase drafts"]},
    {"id": "production", "name": "Production agent", "channel": "production", "reads_as": "P-PRAVEEN",
     "goal": "Keep builds on plan: flag builds whose parts arrive after the planned start, with the part that decides it.",
     "tools": ["timeline", "stock allocation", "lead times"]},
    {"id": "engineering", "name": "Engineering agent", "channel": "engineering", "reads_as": "P-HITHESH",
     "goal": "Keep engineering knowledge true: flag living documents that disagree with the graph, and who maintains them.",
     "tools": ["knowledge health", "decisions", "documents"]},
    {"id": "sales", "name": "Sales agent", "channel": "general", "reads_as": "P-PRAVEEN",
     "goal": "Keep customer promises honest: flag orders that will ship late and by how much (amounts stay in #leadership).",
     "tools": ["timeline", "customer orders", "can we promise"]},
]
BY_ID = {a["id"]: a for a in AGENTS}


def _procurement(graph: Graph, viewer, today: date) -> list[dict]:
    from neura1 import inventory
    out = []
    for i in inventory.items(graph, today):
        f = i.get("forecast") or {}
        if i["status"] == "short" or f.get("late"):
            out.append({"severity": "high", "ref": i["id"], "href": f"/inventory?item={i['id']}",
                        "text": f"{i['id']} ({i['name']}): {i['available']} available after planned builds"
                                + (f"; it should have been ordered by {f['order_by']}" if f.get("late") else "") + "."})
        elif f.get("order_by") and (date.fromisoformat(f["order_by"]) - today).days <= 30:
            out.append({"severity": "medium", "ref": i["id"], "href": f"/inventory?item={i['id']}",
                        "text": f"{i['id']} ({i['name']}): order by {f['order_by']} to stay ahead of planned builds."})
        elif i["status"] == "below_reorder":
            out.append({"severity": "low", "ref": i["id"], "href": f"/inventory?item={i['id']}",
                        "text": f"{i['id']} ({i['name']}) is below its reorder level."})
    return out


def _timeline(graph: Graph, viewer, today: date):
    from neura1 import timeline
    return timeline.timeline(graph, viewer, today)


def _production(graph: Graph, viewer, today: date) -> list[dict]:
    t = _timeline(graph, viewer, today)
    out = []
    for g in t["groups"]:
        for i in g["items"]:
            if i["kind"] == "build" and i["state"] in ("late", "unconfirmed"):
                why = (i["reasons"] or [""])[0]
                out.append({"severity": "high", "ref": i["id"], "href": "/timeline",
                            "text": f"{i['title']} is forecast {i['deviation_days']} days late. {why}"})
    return list({f["ref"]: f for f in out}.values())


def _engineering(graph: Graph, viewer, today: date) -> list[dict]:
    from neura1 import knowledge_health
    s = knowledge_health.sweep(graph, viewer, today)
    out = []
    for d in s["documents"]:
        n = len(d.get("findings") or [])
        if n:
            owner = (d.get("owner") or {}).get("name") if isinstance(d.get("owner"), dict) else d.get("owner")
            out.append({"severity": "medium", "ref": d["id"], "href": "/knowledge",
                        "text": f"{d['title']}: {n} statement{'s disagree' if n != 1 else ' disagrees'} with the graph"
                                + (f"; maintained by {owner}" if owner else "") + "."})
    return out


def _sales(graph: Graph, viewer, today: date) -> list[dict]:
    t = _timeline(graph, viewer, today)
    out = []
    for g in t["groups"]:
        for i in g["items"]:
            if i["kind"] == "order" and i["state"] == "late":
                out.append({"severity": "high", "ref": i["id"], "href": "/timeline",
                            "text": f"{i['title']} will ship about {i['deviation_days']} days late (due {i['plan']['end']}, "
                                    f"forecast {i['forecast']['end']})."})
    return list({f["ref"]: f for f in out}.values())


CHECKS = {"procurement": _procurement, "production": _production, "engineering": _engineering, "sales": _sales}


def run(graph: Graph, agent_id: str, today: date | None = None, post: bool = True) -> dict:
    """One pass of one agent: check, compare with its last report, post what is new."""
    from neura1 import chat
    a = BY_ID[agent_id]
    today = today or date.today()
    viewer = access.viewer(graph, a["reads_as"])
    findings = CHECKS[agent_id](graph, viewer, today)
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order[f["severity"]])
    last = rows(graph, "MATCH (r:AgentRun {agent:$a}) RETURN r.refs AS refs ORDER BY r.at DESC LIMIT 1", {"a": agent_id})
    before = set(last[0]["refs"] or []) if last else set()
    new = [f for f in findings if f["ref"] not in before]
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    posted = False
    if post and findings:
        head = f"**{a['name']}** · {len(findings)} item{'s' if len(findings) != 1 else ''} need attention"
        head += f" ({len(new)} new since my last check)." if before else "."
        lines = [head] + [f"• {f['text']}" for f in findings[:6]]
        if len(findings) > 6:
            lines.append(f"…and {len(findings) - 6} more.")
        chat.ensure_channels(graph)
        msg = "\n".join(lines)
        if not viewer.sees_money:
            msg = access.redact_money_text(msg)
        chat.post(graph, f"chat/{a['channel']}", msg, chat.BOT, None, kind="notice",
                  links=[{"label": "Open", "href": findings[0]["href"]}])
        posted = True
    graph.query("CREATE (r:AgentRun {agent:$a, at:$at, findings:$n, new:$new, refs:$refs})",
                {"a": agent_id, "at": at, "n": len(findings), "new": len(new), "refs": [f["ref"] for f in findings]})
    return {"agent": a, "at": at, "findings": findings, "new": [f["ref"] for f in new], "posted": posted,
            "channel": a["channel"]}


def status(graph: Graph) -> list[dict]:
    out = []
    for a in AGENTS:
        last = rows(graph, "MATCH (r:AgentRun {agent:$a}) RETURN r.at AS at, r.findings AS findings, r.new AS new "
                           "ORDER BY r.at DESC LIMIT 1", {"a": a["id"]})
        out.append(a | {"last": last[0] if last else None})
    return out
