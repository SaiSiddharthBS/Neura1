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
        lines.append(f"• {away} {'person is' if away == 1 else 'people are'} away this week; the leadership team can see the handover plans.")
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
                    post_everyone(get_graph())
            except Exception:
                pass  # try again next minute
            time.sleep(every)

    threading.Thread(target=loop, daemon=True, name="neura1-brief").start()


# ---------- each person's own brief, in their private Neura1 conversation ----------

def personal(graph: Graph, person_id: str, today: date | None = None, shared: dict | None = None) -> dict | None:
    """One person's morning: their work, what waits for them, what changed in what they own, stock running short on
    their parts, pages they maintain that are out of date, and who is away (only what they may see)."""
    from neura1 import access, inventory, knowledge_health, people

    today = today or datetime.now(IST).date()
    v = access.viewer(graph, person_id)
    if not v.id:
        return None
    shared = shared or {}
    day = people.my_day(graph, v, today)
    if day.get("status") != "ok":
        return None
    first = v.name.split()[0]
    work = day["me"]["work"]["current"]
    watching = set(day["watching"])
    lines = [f"Good morning, {first}. Here is your {today:%A %d %B}."]

    if work:
        top = sorted(work, key=lambda w: (w.get("status") != "in_progress", w.get("title") or ""))[:3]
        lines.append(f"• Your work: {len(work)} open. " + "; ".join(f"**{w['title']}**" for w in top) + ".")
    else:
        lines.append("• Nothing is assigned to you right now.")
    if day["approvals"]:
        lines.append("• Waiting for you: " + "; ".join(a["title"] for a in day["approvals"][:3]) + ".")
    since = (today - timedelta(days=1)).isoformat()
    fresh = [n for n in day["news"] if (n.get("ts") or "") >= since and n.get("author") != "Neura1"]
    if fresh:
        lines.append(f"• Changed since yesterday in what you own or work on: {len(fresh)} update"
                     f"{'s' if len(fresh) != 1 else ''}, the latest from {fresh[0]['author'] or fresh[0]['title']} "
                     f"in {fresh[0]['title']}.")
    sig = [s for s in day["signals"] if not s.get("investigation")]
    if sig:
        lines.append("• Signals touching your work: " + "; ".join(
            "a leave notice" if s["kind"] == "leave" else s["title"] for s in sig[:3]) + ".")

    stock = shared.get("stock")
    if stock is None:
        stock = inventory.items(graph, today)
    mine = [r for r in stock if r.get("outlook") and (r["id"] in watching or v.leader)]
    mine.sort(key=lambda r: ((r.get("forecast") or {}).get("order_by") or "9999"))
    if mine:
        lines.append("• Stock: " + " ".join(r["outlook"] for r in mine[:3]))

    health = shared.get("health")
    if health is None:
        health = knowledge_health.sweep(graph, access.Viewer(), today)
    pages = []
    for d in health["documents"]:
        if d["owner_id"] != person_id:
            continue
        seen = [f for f in d["findings"] if f["kind"] != "away" or v.sees_leave_of(f["person"])]
        if seen:
            pages.append((d, len(seen)))
    if pages:
        lines.append("• Pages you maintain: " + "; ".join(
            f"“{d['title']}” has {n} out-of-date fact{'s' if n != 1 else ''}" for d, n in pages) + ".")

    if day["team_away"]:
        lines.append("• Away soon: " + "; ".join(f"{a['name']} {a['start_date']} to {a['end_date']}"
                                                  for a in day["team_away"][:3]) + ".")
    lines.append("Reply here to ask me anything.")
    text = "\n".join(lines)
    if not v.sees_money:
        from neura1.access import MONEY_TEXT
        text = MONEY_TEXT.sub("[amount hidden]", text)
    return {"date": today.isoformat(), "person": person_id, "text": text,
            "links": [{"label": "My day", "href": "/me"}] + ([{"label": "Inventory", "href": "/inventory"}] if mine else [])
            + ([{"label": "Knowledge health", "href": "/knowledge"}] if pages else [])}


def post_personal(graph: Graph, person_id: str, today: date | None = None, force: bool = False,
                  shared: dict | None = None) -> dict | None:
    from neura1 import chat
    today = today or datetime.now(IST).date()
    if not force and rows(graph, "MATCH (x:Brief {date:$d, person:$p}) RETURN count(x) AS n",
                          {"d": today.isoformat(), "p": person_id})[0]["n"]:
        return None
    b = personal(graph, person_id, today, shared)
    if not b:
        return None
    cid = chat.bot_channel(graph, person_id)
    chat.post(graph, cid, b["text"], chat.BOT, None, kind="brief", links=b["links"])
    graph.query("MERGE (x:Brief {date:$d, person:$p}) SET x.posted_at = $at",
                {"d": b["date"], "p": person_id, "at": datetime.now(IST).isoformat()})
    return b | {"channel": cid}


def post_everyone(graph: Graph, today: date | None = None) -> int:
    """Everyone's brief, computing the company-wide parts once."""
    from neura1 import inventory, knowledge_health
    from neura1.access import Viewer
    today = today or datetime.now(IST).date()
    people = rows(graph, "MATCH (p:Person) RETURN count(p) AS n")[0]["n"]
    done = rows(graph, "MATCH (x:Brief {date:$d}) WHERE x.person IS NOT NULL RETURN count(DISTINCT x.person) AS n",
                {"d": today.isoformat()})[0]["n"]
    if done >= people:
        return 0  # everyone has today's brief: nothing to compute
    shared = {"stock": inventory.items(graph, today), "health": knowledge_health.sweep(graph, Viewer(), today)}
    sent = 0
    for p in rows(graph, "MATCH (p:Person) RETURN p.id AS id ORDER BY id"):
        try:
            sent += 1 if post_personal(graph, p["id"], today, shared=shared) else 0
        except Exception:
            continue  # one person's brief must not stop the others
    return sent
