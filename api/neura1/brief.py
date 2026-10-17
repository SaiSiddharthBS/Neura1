"""The morning brief: Neura1 posts what the company needs to know today, on its own, at 09:00 IST.

The brief goes to #general, which everyone reads, so it carries no amounts, no leave dates or names, and no names in
the skills line: only what every reader may see. Each day's brief is recorded as a (:Brief {date}) node, so it is
posted once even if the server restarts.
"""

import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from falkordb import Graph

from neura1.graph import rows

IST = ZoneInfo("Asia/Kolkata")
HOUR = 9


def compose(graph: Graph, today: date | None = None) -> dict:
    from neura1 import capabilities, scenarios
    from neura1.access import Viewer

    today = today or datetime.now(IST).date()
    t, soon, yesterday = today.isoformat(), (today + timedelta(days=14)).isoformat(), (today - timedelta(days=1)).isoformat()
    signals = [s for s in scenarios.signals(graph) if not s.get("investigation")]
    work = rows(graph, "MATCH (a:Action) RETURN coalesce(a.status, 'open') AS status, count(*) AS n")
    by = {w["status"]: w["n"] for w in work}
    finished = rows(graph, "MATCH (a:Action) WHERE a.status = 'done' AND a.completed_at >= $y RETURN a.title AS title",
                    {"y": yesterday})
    builds = rows(graph, """MATCH (b:Build)-[:BUILDS]->(r:Revision) WHERE b.planned_date >= $t AND b.planned_date <= $soon
                            RETURN b.id AS id, r.id AS revision, b.planned_date AS date ORDER BY date""",
                  {"t": t, "soon": soon})
    quotes = rows(graph, """MATCH (q:Quote)-[:FOR]->(i:Item) WHERE q.valid_until >= $t AND q.valid_until <= $limit
                            RETURN q.id AS id, i.id AS item, q.valid_until AS until ORDER BY until""",
                  {"t": t, "limit": (today + timedelta(days=75)).isoformat()})
    away = rows(graph, """MATCH (p:Person)-[:HAS_ABSENCE]->(a:Absence)
                          WHERE a.start_date <= $week AND a.end_date >= $t RETURN count(DISTINCT p) AS n""",
                {"t": t, "week": (today + timedelta(days=7)).isoformat()})[0]["n"]
    cmap = capabilities.company_map(graph, Viewer(id="P-NOBODY", name="Everyone"), today)
    thin = [s["skill"] for s in cmap["skills"] if s["status"] == "thin" and s["open_tasks"]][:3]

    lines = [f"Good morning. Here is Flyvi on {today:%A %d %B}."]
    if signals:
        # A leave signal is named generically: who is on leave is not for #general.
        titles = ["a leave notice (handover plan ready)" if s["kind"] == "leave" else s["title"] for s in signals[:3]]
        lines.append(f"• {len(signals)} signal{'s' if len(signals) != 1 else ''} waiting for a decision: "
                     + "; ".join(titles) + ".")
    else:
        lines.append("• No signal is waiting for a decision.")
    lines.append(f"• Work in flight: {by.get('in_progress', 0)} in progress, {by.get('open', 0)} to do, "
                 f"{by.get('blocked', 0)} blocked" + (f"; {len(finished)} finished since yesterday." if finished else "."))
    if builds:
        lines.append("• Builds in the next 14 days: " + ", ".join(f"{b['id']} ({b['revision']}, {b['date']})" for b in builds[:4]) + ".")
    if quotes:
        lines.append("• Quotes expiring soon: " + ", ".join(f"{q['id']} for {q['item']} on {q['until']}" for q in quotes[:4]) + ".")
    if thin:
        lines.append("• Held by one person, with open work: " + ", ".join(thin) + ".")
    if away:
        lines.append(f"• {away} {'person is' if away == 1 else 'people are'} away this week; managers can see the handover plans.")
    return {"date": t, "text": "\n".join(lines), "signals": len(signals), "builds": builds, "quotes": quotes,
            "thin": thin, "away": away}


def post(graph: Graph, today: date | None = None, force: bool = False) -> dict | None:
    """Post today's brief to #general once (or again, when forced)."""
    from neura1 import chat

    b = compose(graph, today)
    already = rows(graph, "MATCH (x:Brief {date:$d}) RETURN count(x) AS n", {"d": b["date"]})[0]["n"]
    if already and not force:
        return None
    chat.ensure_channels(graph)
    chat.post(graph, "chat/general", b["text"], chat.BOT, None, kind="brief",
              links=[{"label": "Signals", "href": "/signals"}, {"label": "Workboard", "href": "/board"},
                     {"label": "Capability map", "href": "/capabilities"}])
    graph.query("MERGE (x:Brief {date:$d}) SET x.posted_at = $at", {"d": b["date"], "at": datetime.now(IST).isoformat()})
    return b


_started = False


def start_scheduler(get_graph, every: float = 60.0) -> None:
    """Post the brief at 09:00 IST each day (or at start-up, if the server starts later in the day)."""
    global _started
    if _started:
        return
    _started = True

    def loop():
        while True:
            try:
                if datetime.now(IST).hour >= HOUR:
                    post(get_graph())
            except Exception:
                pass  # try again next minute
            time.sleep(every)

    threading.Thread(target=loop, daemon=True, name="neura1-brief").start()
