"""Neura1 Chat: the company's own chat, where every message is company knowledge the moment it is sent.

Messages are stored as passages (Chunk) of a chat Source, so they are linked to the people, parts, orders and
projects they name, feed who-knows-what, search and What's new, and can be cited by the agent. In a channel:
  * `@neura1 <question>` asks the company brain; the answer is posted back with its sources.
  * `/impact <part> [price] [lead weeks]`, `/who <topic>`, `/away <person>`, `/risk`, `/help` run graph tools
    directly, with no model.
Neura1 also posts on its own when something happens that a channel should know (see `notify`).
"""

import hashlib
import json
import re
import threading
from datetime import date, datetime, timezone
from decimal import Decimal

from falkordb import Graph

from neura1 import brain, scenarios
from neura1 import access
from neura1.access import MONEY_TEXT
from neura1.graph import rows
from neura1.ingest.unstructured import entity_lexicon, mentions

BOT = "Neura1"
DEFAULT_CHANNELS = [("general", "Everyone at Flyvi"), ("engineering", "R&D hardware, software and testing"),
                    ("supply", "Purchase, stores and suppliers"), ("production", "Builds and deliveries"),
                    ("leadership", "Leadership team")]
# Where Neura1 posts on its own, by kind of event.
ROUTES = {"supplier_change": "supply", "evidence": "engineering", "plan": "general", "escalation": "leadership",
          "absence": "general", "task_done": "general"}


MONEY_CHANNELS = {"chat/leadership", "chat/supply"}


class Audience:
    """Who will read a reply in this channel. Replies only contain what every reader may see."""

    def __init__(self, graph: Graph, channel_id: str):
        from neura1.access import viewer
        ch = rows(graph, "MATCH (c:Channel {id:$id}) RETURN c.kind AS kind, c.members AS members", {"id": channel_id})
        self.dm = bool(ch) and ch[0]["kind"] == "dm"
        self.readers = [viewer(graph, m) for m in (ch[0]["members"] or [])] if self.dm else []
        self.money = channel_id in MONEY_CHANNELS or (self.dm and all(r.sees_money for r in self.readers))

    def sees_leave_of(self, person_id: str) -> bool:
        return self.dm and all(r.sees_leave_of(person_id) for r in self.readers)




def redact_text(text: str, audience: "Audience") -> str:
    return text if audience.money else MONEY_TEXT.sub("[amount hidden in this channel]", text)


def _now() -> str:
    # Microseconds keep a message and Neura1's immediate reply in the right order.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def ensure_channels(graph: Graph) -> None:
    for name, purpose in DEFAULT_CHANNELS:
        graph.query("MERGE (c:Channel {id:$id}) ON CREATE SET c.name=$name, c.purpose=$p, c.kind='channel'",
                    {"id": f"chat/{name}", "name": name, "p": purpose})


def channels(graph: Graph, viewer_id: str | None) -> list[dict]:
    ensure_channels(graph)
    return rows(graph, """
        MATCH (c:Channel) WHERE c.kind = 'channel' OR $me IN c.members
        OPTIONAL MATCH (m)-[:PART_OF]->(s:Source) WHERE s.id = c.id AND (m:Chunk OR m:Message)
        RETURN c.id AS id, c.name AS name, c.purpose AS purpose, c.kind AS kind, c.members AS members,
               count(m) AS messages, max(m.ts) AS last
        ORDER BY kind, name
    """, {"me": viewer_id or ""})


def dm_channel(graph: Graph, a: str, b: str) -> str:
    pair = sorted([a, b])
    cid = f"chat/dm-{pair[0]}-{pair[1]}".lower()
    names = {r["id"]: r["name"] for r in rows(graph, "MATCH (p:Person) WHERE p.id IN $ids RETURN p.id AS id, p.name AS name",
                                              {"ids": pair})}
    graph.query("""MERGE (c:Channel {id:$id}) ON CREATE SET c.kind='dm', c.members=$m, c.name=$name""",
                {"id": cid, "m": pair, "name": " & ".join(names.get(p, p) for p in pair)})
    return cid


def messages(graph: Graph, channel_id: str, after: str | None = None, limit: int = 200) -> list[dict]:
    return rows(graph, """
        MATCH (m)-[:PART_OF]->(:Source {id:$ch})
        WHERE (m:Chunk OR m:Message) AND ($after IS NULL OR m.ts > $after)
        OPTIONAL MATCH (m)-[:MENTIONS|REFERS_TO]->(x) WHERE NOT x:Source
        RETURN m.id AS id, m.text AS text, m.author AS author, m.author_id AS author_id, m.ts AS ts, m.kind AS kind,
               m.sources AS sources, m.links AS links,
               collect(DISTINCT {id: x.id, label: labels(x)[0], name: coalesce(x.name, x.id)}) AS about
        ORDER BY ts LIMIT $limit
    """, {"ch": channel_id, "after": after, "limit": limit})


def post(graph: Graph, channel_id: str, text: str, author: str, author_id: str | None, kind: str = "message",
         sources: list[str] | None = None, links: list[dict] | None = None) -> dict:
    """Store one message and link it to what it names.

    Channel messages become company knowledge: `Chunk` passages that search, "who knows" and timelines use.
    Direct messages stay private by construction: they are `Message` nodes that no knowledge query matches.
    """
    ts = _now()
    mid = f"{channel_id}#" + hashlib.sha256(f"{author}|{ts}|{text}".encode()).hexdigest()[:10]
    channel = rows(graph, "MATCH (c:Channel {id:$id}) RETURN c.name AS name, c.kind AS kind", {"id": channel_id})
    private = bool(channel) and channel[0]["kind"] == "dm"
    title = "Neura1 Chat (direct)" if private else f"Neura1 Chat #{channel[0]['name'] if channel else channel_id}"
    label, link = ("Message", "REFERS_TO") if private else ("Chunk", "MENTIONS")
    graph.query(f"""
        MERGE (s:Source {{id:$sid}}) ON CREATE SET s.kind=$skind, s.title=$title, s.authority='source_document',
                                                 s.uri=$sid, s.first_seen=$ts
        SET s.updated_at=$ts
        CREATE (m:{label} {{id:$mid, text:$text, author:$author, author_id:$aid, ts:$ts, kind:$kind,
                         source_version:'live', text_hash:$hash, ordinal:0, sources:$sources, links:$links}})
        CREATE (m)-[:PART_OF]->(s)
        WITH m OPTIONAL MATCH (p:Person {{id:$aid}})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (m)-[:SAID_BY]->(p))
    """, {"sid": channel_id, "skind": "dm" if private else "chat", "title": title, "mid": mid, "text": text,
          "author": author, "aid": author_id, "ts": ts, "kind": kind, "hash": hashlib.sha256(text.encode()).hexdigest()[:12],
          "sources": json.dumps(sources or []), "links": json.dumps(links or [])})
    targets = sorted(mentions(text, entity_lexicon(graph)) - {channel_id})
    if targets:
        graph.query(f"MATCH (m:{label} {{id:$mid}}) UNWIND $t AS tid MATCH (x {{id:tid}}) MERGE (m)-[:{link}]->(x)",
                    {"mid": mid, "t": targets})
    if not private:
        _embed_later(graph, mid, text)
    return {"id": mid, "ts": ts, "about": targets}


def _embed_later(graph: Graph, mid: str, text: str) -> None:
    def work():
        try:
            from neura1.llm import embed
            v = embed([text])[0]
            graph.query("MATCH (m:Chunk {id:$id}) SET m.embedding = vecf32($v)", {"id": mid, "v": v})
        except Exception:
            pass  # semantic search simply will not see this message; keyword search and links still do
    threading.Thread(target=work, daemon=True).start()


# ---------- commands, answered from the graph without a model ----------

HELP = ("Try: `/impact NB54360 320 22` (price and lead time are optional), `/who CAN bus`, `/away Raghavendra`, "
        "`/risk`, or ask anything with `@neura1`.")


def _money(v) -> str:
    return f"₹{int(round(float(v))):,}" if v not in (None, "") else "unknown"


def command(graph: Graph, text: str, audience: "Audience | None" = None) -> dict:
    parts = text.strip().split()
    cmd, args = parts[0].lower(), parts[1:]
    if cmd == "/help":
        return {"text": HELP}
    if cmd == "/impact" and args:
        from neura1.impact import ChangeEvent, analyse
        price = Decimal(args[1]) if len(args) > 1 and re.fullmatch(r"[\d.]+", args[1]) else None
        lead = int(args[2]) if len(args) > 2 and args[2].isdigit() else None
        r = analyse(graph, ChangeEvent(args[0], price, "INR", None, lead, date.today()))
        if r["status"] != "ok":
            sugg = ", ".join(c["id"] for c in r.get("candidates", [])) or "nothing similar"
            return {"text": f"No part is exactly `{args[0]}`. Did you mean: {sugg}?"}
        used = ", ".join(f"{u['revision']} ({u['qty_per_unit']}/unit)" for u in r["where_used"] if u["applicable"])
        risk = [b for b in r["builds"] if b["at_risk"]]
        orders = [o for b in r["builds"] for o in b["orders"]]
        rejected = [a["id"] for a in r["alternates"] if a["status"] == "rejected"]
        lines = [f"**{r['part']['id']}** is used in {used or 'no released product'}."]
        if r["cost"] and (audience is None or audience.money):
            lines.append(f"Cost increase {_money(r['cost']['total_delta'])} ({r['cost']['formula']}).")
        elif r["cost"]:
            lines.append("Cost figures are visible in #leadership and #supply.")
        if risk:
            lines.append(f"{len(risk)} builds at risk; orders exposed: {', '.join(o['order'] + ' ' + o['customer'] for o in orders)}.")
        if rejected:
            lines.append(f"Do not switch to {', '.join(rejected)}: rejected before (see decisions).")
        lines.append(f"{len(r['actions'])} tasks proposed under HB-ENG-04.")
        q = f"item={r['part']['id']}" + (f"&price={price}" if price else "") + (f"&lead={lead}" if lead else "")
        return {"text": " ".join(lines), "links": [{"label": "Open impact", "href": f"/impact?{q}"}]}
    if cmd == "/who" and args:
        r = brain.who_knows(graph, " ".join(args))
        if not r["subject"]:
            names = ", ".join(f"{b['name']} ({b['passages']})" for b in r.get("by_text", [])) or "nobody yet"
            return {"text": f"Nothing is called `{' '.join(args)}`. People who wrote about it: {names}."}
        top = "; ".join(f"**{p['name']}** ({', '.join(sorted({s['signal'] for s in p['signals']})[:3])})"
                        for p in r["people"][:4])
        return {"text": f"Who knows {r['subject']['name']}: {top or 'nobody recorded'}.",
                "links": [{"label": "Who knows", "href": f"/brain?who={r['subject']['id']}"}]}
    if cmd == "/away" and args:
        found = rows(graph, "MATCH (p:Person) WHERE toLower(p.name) STARTS WITH toLower($n) RETURN p.id AS id",
                     {"n": args[0]})
        if len(found) != 1:
            return {"text": f"{len(found)} people match `{args[0]}`."}
        a = scenarios.absence_impact(graph, found[0]["id"])
        if not a["absence"]["start"]:
            return {"text": f"{a['person']['name']} has no leave recorded."}
        if audience is not None and not audience.sees_leave_of(found[0]["id"]):
            return {"text": (f"{a['person']['name']} has leave planned. Dates and the handover plan are visible to their "
                             f"manager, backup, HR and leadership on the handover page."),
                    "links": [{"label": "Handover plan", "href": f"/people?id={found[0]['id']}&absence=1"}]}
        return {"text": (f"{a['person']['name']} is away {a['absence']['start']} → {a['absence']['end']}. "
                         f"Backup: {a['person']['backup'] or 'none'}. {len(a['conflicts'])} conflicts, "
                         f"{len(a['actions'])} handover tasks proposed."),
                "links": [{"label": "Handover plan", "href": f"/people?id={found[0]['id']}&absence=1"}]}
    if cmd == "/risk":
        r = scenarios.risk_radar(graph)
        s = r["single_source"][0] if r["single_source"] else None
        b = r["bus_factor"][0] if r["bus_factor"] else None
        c = r["chokepoints"][0] if r["chokepoints"] else None
        bits = []
        if s:
            bits.append(f"single-sourced **{s['id']}** with {_money(s['value_at_risk'])} of orders behind it")
        if b:
            bits.append(f"**{b['id']}** knowledge sits mostly with {b['person']}")
        if c:
            bits.append(f"biggest chokepoint is {c['name']}")
        text = "Top risks: " + "; ".join(bits) + "."
        return {"text": redact_text(text, audience) if audience else text, "links": [{"label": "Risk radar", "href": "/risk"}]}
    return {"text": HELP}


# ---------- @neura1 ----------

def ask_in_channel(graph: Graph, channel_id: str, question: str, asker_id: str | None) -> None:
    """Answer in the background and post the reply; uses one conversation per channel for follow-ups."""
    from neura1 import agent, memory

    def work():
        try:
            conv = rows(graph, "MATCH (c:Channel {id:$id}) RETURN c.conversation AS conv", {"id": channel_id})
            cid = conv[0]["conv"] if conv and conv[0]["conv"] else None
            if not cid:
                cid = memory.start(graph, asker_id, question)
                # Questions asked in a direct message are never shared through recall.
                graph.query("MATCH (c:Channel {id:$id}) SET c.conversation=$cid WITH c "
                            "MATCH (v:Conversation {id:$cid}) SET v.private = (c.kind = 'dm')", {"id": channel_id, "cid": cid})
            audience = Audience(graph, channel_id)
            result = agent.ask(graph, question, history=memory.history(graph, cid),
                               restrict={"money": audience.money, "leave_of": audience.sees_leave_of,
                                         "hidden": access.hidden_sources(graph, audience.sees_leave_of)})
            memory.record(graph, cid, question, result)
            text = redact_text(result["answer"], audience)
            if result.get("warnings"):
                text += "\n\n" + "\n".join(result["warnings"])
            post(graph, channel_id, text, BOT, None, kind="answer", sources=result.get("sources", []))
        except Exception as exc:
            post(graph, channel_id, f"I could not answer that right now ({exc}). Graph commands like /impact still work.",
                 BOT, None, kind="error")

    threading.Thread(target=work, daemon=True).start()


def handle(graph: Graph, channel_id: str, text: str, author: str, author_id: str | None) -> dict:
    msg = post(graph, channel_id, text, author, author_id)
    stripped = text.strip()
    if stripped.startswith("/"):
        reply = command(graph, stripped, Audience(graph, channel_id))
        post(graph, channel_id, reply["text"], BOT, None, kind="command", links=reply.get("links"))
    elif re.search(r"@neura1\b", text, re.I):
        ask_in_channel(graph, channel_id, re.sub(r"@neura1\b", "", text, flags=re.I).strip(), author_id)
        msg["thinking"] = True
    return msg


# ---------- Neura1 speaks first ----------

def notify(graph: Graph, kind: str, text: str, links: list[dict] | None = None) -> None:
    """Post a proactive message to the channel that should know about this kind of event."""
    try:
        ensure_channels(graph)
        post(graph, f"chat/{ROUTES.get(kind, 'general')}", text, BOT, None, kind="notice", links=links)
    except Exception:
        pass  # a failed notification must never break the action that triggered it
