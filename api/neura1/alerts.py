"""Alerts out of Neura1: a short, permission-filtered message to the channel where people and agents (Dots) work.

Slack incoming webhooks and Microsoft Teams workflow webhooks both accept {"text": "..."}; Dots read and post in Slack
and Teams. Off unless NEURA1_AGENT_ALERT_WEBHOOK is set. Messages are written for the external-agent reader, so they
carry no amounts and no one's leave.
"""

import json
import urllib.request

from falkordb import Graph

from neura1.config import settings


def digest(graph: Graph) -> str:
    from neura1 import timeline
    from neura1.agent_mcp import agent_viewer
    t = timeline.timeline(graph, agent_viewer(graph))
    s = t["summary"]
    lines = [f"Neura1 · plan check for {t['today']}: {s['late']} item{'s' if s['late'] != 1 else ''} late, "
             f"{s['projects_late']} project{'s' if s['projects_late'] != 1 else ''} past target, {s['at_risk']} at risk."]
    for w in s["worst"]:
        name = w["title"] if w["id"] in w["title"] else f"{w['id']} {w['title']}"
        lines.append(f"• {name}: {w['deviation_days']} days late. {w['reason']}")
    for g in t["groups"]:
        if (g["deviation_days"] or 0) > 0:
            lines.append(f"• Project {g['name']}: target {g['plan']['end']}, forecast {g['forecast']['end']}.")
    return "\n".join(lines)


def post(text: str, url: str | None = None) -> dict:
    url = url or settings.agent_alert_webhook
    if not url:
        return {"sent": False, "reason": "No alert webhook is set (NEURA1_AGENT_ALERT_WEBHOOK)."}
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return {"sent": 200 <= r.status < 300, "status": r.status}
    except Exception as exc:  # the channel being down never breaks Neura1
        return {"sent": False, "reason": str(exc)}
