"""Neura1 Chat: the company's own messenger, where every channel message is company knowledge the moment it is sent.

Three kinds of conversation:
  * **channels** (#general, #engineering, ... and any channel someone creates) are open to everyone. Their messages
    are passages (Chunk) of a chat Source, linked to the people, parts, orders and projects they name, so they feed
    search, who-knows-what and What's new, and can be cited by the agent;
  * **direct messages** between two people, and
  * **groups** of people chosen by whoever creates them. Both are private by construction: their messages are
    `Message` nodes that no knowledge query matches, and only members can read them.

Everything a messenger needs: unread counts and @mentions, replies, edits, deletes, emoji reactions, read receipts,
typing indicators, presence and search. In any conversation:
  * `@neura1 <question>` asks the company brain; the answer is posted back with its sources.
  * `/impact <part> [price] [lead weeks]`, `/slips`, `/who <topic>`, `/away <person>`, `/risk`, `/help` run graph tools
    directly, with no model.
Neura1 also posts on its own when something happens that a channel should know (see `notify`).
"""

import hashlib
import json
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from falkordb import Graph

from neura1 import access, brain, scenarios
from neura1.access import MONEY_TEXT
from neura1.graph import rows
from neura1.ingest.unstructured import entity_lexicon, mentions

BOT = "Neura1"
DEFAULT_CHANNELS = [("general", "Everyone at Flyvi"), ("engineering", "R&D hardware, software and testing"),
                    ("supply", "Purchase, stores and suppliers"), ("production", "Builds and deliveries"),
                    ("leadership", "Directors and the leadership team")]
# Where Neura1 posts on its own, by kind of event.
ROUTES = {"supplier_change": "supply", "evidence": "engineering", "plan": "general", "escalation": "leadership",
          "absence": "general", "task_done": "general"}

MONEY_CHANNELS = {"chat/leadership"}
PRIVATE = ("dm", "group", "bot")  # "bot": a person's own conversation with Neura1
REACTIONS = ["👍", "❤️", "😂", "🎉", "👀", "✅", "🙏", "🔥"]
MAX_TEXT = 4000

# Who is typing where, and who was last seen when. Kept in memory: they only matter for a few seconds.
_typing: dict[str, dict[str, tuple[str, float]]] = {}
_seen: dict[str, float] = {}
_lock = threading.Lock()


class ChatError(Exception):
    """A request the chat refuses, with the reason shown to the person (status like HTTP: 400, 403, 404)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Audience:
    """Who will read a reply in this conversation. Replies only contain what every reader may see."""

    def __init__(self, graph: Graph, channel_id: str):
        from neura1.access import viewer
        ch = rows(graph, "MATCH (c:Channel {id:$id}) RETURN c.kind AS kind, c.members AS members", {"id": channel_id})
        self.private = bool(ch) and ch[0]["kind"] in PRIVATE
        self.dm = self.private  # kept for callers that predate groups
        self.readers = [viewer(graph, m) for m in (ch[0]["members"] or [])] if self.private else []
        self.money = channel_id in MONEY_CHANNELS or (self.private and bool(self.readers)
                                                      and all(r.sees_money for r in self.readers))

    def sees_leave_of(self, person_id: str) -> bool:
        return self.private and bool(self.readers) and all(r.sees_leave_of(person_id) for r in self.readers)


def redact_text(text: str, audience: "Audience") -> str:
    return text if audience.money else MONEY_TEXT.sub("[amount hidden in this channel]", text)


def _now() -> str:
    # Microseconds keep a message and Neura1's immediate reply in the right order.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _names(graph: Graph) -> dict[str, str]:
    return {r["id"]: r["name"] for r in rows(graph, "MATCH (p:Person) RETURN p.id AS id, p.name AS name")}


# ---------- conversations ----------

def ensure_channels(graph: Graph) -> None:
    for name, purpose in DEFAULT_CHANNELS:
        graph.query("MERGE (c:Channel {id:$id}) ON CREATE SET c.name=$name, c.purpose=$p, c.kind='channel', c.default=true",
                    {"id": f"chat/{name}", "name": name, "p": purpose})


def channel(graph: Graph, channel_id: str) -> dict | None:
    found = rows(graph, """MATCH (c:Channel {id:$id}) RETURN c.id AS id, c.kind AS kind, c.name AS name,
                           c.purpose AS purpose, c.members AS members, c.created_by AS created_by,
                           coalesce(c.default, false) AS default""", {"id": channel_id})
    return found[0] if found else None


def may_read(ch: dict, viewer: "access.Viewer") -> None:
    """Raise ChatError unless this viewer may read (and so write in) the conversation."""
    if ch["kind"] in PRIVATE and viewer.id not in (ch["members"] or []):
        raise ChatError(403, "This conversation is visible to its members only")
    if ch["id"] in MONEY_CHANNELS and not viewer.sees_money:
        raise ChatError(403, "This channel discusses prices and order values; it is open to the directors and the "
                             "leadership team")


def channels(graph: Graph, viewer_id: str | None, viewer_name: str | None = None) -> list[dict]:
    """Every conversation the viewer can open, with unread counts, @mentions and the latest message."""
    ensure_channels(graph)
    me = viewer_id or ""
    names = _names(graph)
    viewer_name = viewer_name or names.get(me, "")
    found = rows(graph, """
        MATCH (c:Channel) WHERE c.kind = 'channel' OR $me IN c.members
        OPTIONAL MATCH (:Person {id:$me})-[r:READ_UP_TO]->(c)
        OPTIONAL MATCH (m)-[:PART_OF]->(s:Source) WHERE s.id = c.id AND (m:Chunk OR m:Message)
        WITH c, coalesce(r.ts, '') AS read, m
        RETURN c.id AS id, c.name AS name, c.purpose AS purpose, c.kind AS kind, c.members AS members,
               c.created_by AS created_by, coalesce(c.default, false) AS default, c.created_at AS created_at,
               count(m) AS messages, max(m.ts) AS last,
               sum(CASE WHEN m IS NOT NULL AND m.ts > read AND coalesce(m.author_id, '') <> $me
                        AND NOT coalesce(m.deleted, false) AND coalesce(m.kind, '') <> 'system' THEN 1 ELSE 0 END) AS unread,
               sum(CASE WHEN m IS NOT NULL AND m.ts > read AND coalesce(m.author_id, '') <> $me AND $at <> '@'
                        AND NOT coalesce(m.deleted, false) AND toLower(m.text) CONTAINS $at THEN 1 ELSE 0 END) AS mentions
    """, {"me": me, "at": "@" + (viewer_name or "").lower()})
    last = rows(graph, """
        UNWIND $pairs AS p
        MATCH (m)-[:PART_OF]->(:Source {id:p.id}) WHERE (m:Chunk OR m:Message) AND m.ts = p.ts
        RETURN p.id AS id, m.author AS author, m.author_id AS author_id, m.text AS text,
               coalesce(m.deleted, false) AS deleted, m.kind AS kind
    """, {"pairs": [{"id": c["id"], "ts": c["last"]} for c in found if c["last"]]})
    preview = {x["id"]: x for x in last}
    if me:
        _seen[me] = time.time()
    out = []
    for c in found:
        members = [{"id": m, "name": names.get(m, m), "online": _online(m)} for m in (c["members"] or [])]
        name = c["name"]
        if c["kind"] == "dm":
            other = [m for m in members if m["id"] != me] or members
            name = other[0]["name"] if other else name
        p = preview.get(c["id"])
        out.append(c | {"name": name, "members": members, "unread": int(c["unread"] or 0), "mentions": int(c["mentions"] or 0),
                        "preview": None if not p else {"author": p["author"], "mine": p["author_id"] == me and bool(me),
                                                       "text": "Message deleted" if p["deleted"] else (p["text"] or "")[:140],
                                                       "kind": p["kind"]}})
    order = {"channel": 0, "bot": 1, "group": 2, "dm": 2}
    return sorted(out, key=lambda c: (order.get(c["kind"], 3), -_ts_key(c["last"] or c["created_at"]) if c["kind"] != "channel" else 0,
                                      c["name"].lower()))


def _ts_key(ts: str | None) -> float:
    try:
        return datetime.fromisoformat(ts).timestamp() if ts else 0.0
    except ValueError:
        return 0.0


def unread(graph: Graph, viewer_id: str | None, viewer_name: str | None = None) -> dict:
    cs = channels(graph, viewer_id, viewer_name) if viewer_id else []
    return {"total": sum(c["unread"] for c in cs), "mentions": sum(c["mentions"] for c in cs),
            "conversations": sum(1 for c in cs if c["unread"])}


def dm_channel(graph: Graph, a: str, b: str) -> str:
    if a == b:
        raise ChatError(400, "Choose someone else to message")
    pair = sorted([a, b])
    names = _names(graph)
    if any(p not in names for p in pair):
        raise ChatError(404, "Unknown person")
    cid = f"chat/dm-{pair[0]}-{pair[1]}".lower()
    graph.query("""MERGE (c:Channel {id:$id}) ON CREATE SET c.kind='dm', c.members=$m, c.name=$name, c.created_at=$ts""",
                {"id": cid, "m": pair, "name": " & ".join(names[p] for p in pair), "ts": _now()})
    return cid


def bot_channel(graph: Graph, person_id: str) -> str:
    """The person's private conversation with Neura1: their morning brief, and questions without @neura1."""
    if person_id not in _names(graph):
        raise ChatError(404, "Unknown person")
    cid = f"chat/neura1-{person_id}".lower()
    graph.query("""MERGE (c:Channel {id:$id}) ON CREATE SET c.kind='bot', c.members=$m, c.name='Neura1',
                   c.purpose='Your brief every morning, and anything you want to ask', c.created_at=$ts""",
                {"id": cid, "m": [person_id], "ts": _now()})
    return cid


def create_group(graph: Graph, creator_id: str, name: str, member_ids: list[str]) -> str:
    names = _names(graph)
    name = re.sub(r"\s+", " ", name or "").strip()[:60]
    members = sorted({creator_id, *member_ids})
    if not name:
        raise ChatError(400, "Give the group a name")
    if any(m not in names for m in members):
        raise ChatError(404, "Unknown person")
    if len(members) < 3:
        raise ChatError(400, "A group needs at least two other people; message one person directly instead")
    cid = f"chat/grp-{uuid.uuid4().hex[:10]}"
    graph.query("""CREATE (c:Channel {id:$id, kind:'group', name:$name, members:$m, created_by:$by, created_at:$ts})""",
                {"id": cid, "name": name, "m": members, "by": creator_id, "ts": _now()})
    others = ", ".join(names[m] for m in members if m != creator_id)
    _system(graph, cid, f"{names[creator_id]} created the group and added {others}")
    return cid


def create_channel(graph: Graph, creator_id: str, name: str, purpose: str | None) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", (name or "").lower()).strip("-")[:40]
    if not slug:
        raise ChatError(400, "Give the channel a name (letters, numbers and dashes)")
    cid = f"chat/{slug}"
    if channel(graph, cid):
        raise ChatError(409, f"#{slug} already exists")
    graph.query("""CREATE (c:Channel {id:$id, kind:'channel', name:$name, purpose:$p, created_by:$by, created_at:$ts})""",
                {"id": cid, "name": slug, "p": (purpose or "").strip()[:140] or None, "by": creator_id, "ts": _now()})
    _system(graph, cid, f"{_names(graph).get(creator_id, creator_id)} created #{slug}")
    return cid


def update_conversation(graph: Graph, channel_id: str, by_id: str, name: str | None = None,
                        purpose: str | None = None) -> None:
    ch = channel(graph, channel_id)
    if not ch:
        raise ChatError(404, "Unknown conversation")
    if ch["kind"] in ("dm", "bot") or ch["default"]:
        raise ChatError(400, "This conversation cannot be renamed")
    if ch["kind"] == "group" and by_id not in (ch["members"] or []):
        raise ChatError(403, "Only members can change the group")
    if ch["kind"] == "channel" and ch["created_by"] != by_id:
        raise ChatError(403, "Only the person who created the channel can change it")
    who = _names(graph).get(by_id, by_id)
    if name is not None and name.strip() and name.strip() != ch["name"]:
        new = name.strip()[:60] if ch["kind"] == "group" else re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:40]
        graph.query("MATCH (c:Channel {id:$id}) SET c.name=$n", {"id": channel_id, "n": new})
        _system(graph, channel_id, f"{who} renamed the {'group' if ch['kind'] == 'group' else 'channel'} to {new}")
    if purpose is not None and purpose.strip() != (ch["purpose"] or ""):
        graph.query("MATCH (c:Channel {id:$id}) SET c.purpose=$p", {"id": channel_id, "p": purpose.strip()[:140] or None})
        _system(graph, channel_id, f"{who} changed the description")


def add_members(graph: Graph, channel_id: str, by_id: str, person_ids: list[str]) -> list[str]:
    ch = channel(graph, channel_id)
    if not ch or ch["kind"] != "group":
        raise ChatError(400, "People can only be added to a group")
    if by_id not in ch["members"]:
        raise ChatError(403, "Only members can add people")
    names = _names(graph)
    new = sorted({p for p in person_ids if p in names} - set(ch["members"]))
    if not new:
        return ch["members"]
    members = sorted(set(ch["members"]) | set(new))
    graph.query("MATCH (c:Channel {id:$id}) SET c.members=$m", {"id": channel_id, "m": members})
    _system(graph, channel_id, f"{names.get(by_id, by_id)} added {', '.join(names[p] for p in new)}")
    return members


def remove_member(graph: Graph, channel_id: str, by_id: str, person_id: str) -> list[str]:
    """Leave a group (person_id == by_id), or remove someone from it (the group's creator only)."""
    ch = channel(graph, channel_id)
    if not ch or ch["kind"] != "group":
        raise ChatError(400, "Only groups have members to remove")
    if person_id not in ch["members"]:
        raise ChatError(404, "Not a member of this group")
    if person_id != by_id and ch["created_by"] != by_id:
        raise ChatError(403, "Only the person who created the group can remove others")
    members = [m for m in ch["members"] if m != person_id]
    names = _names(graph)
    graph.query("""MATCH (c:Channel {id:$id}) SET c.members=$m
                   WITH c OPTIONAL MATCH (:Person {id:$p})-[r:READ_UP_TO]->(c) DELETE r""",
                {"id": channel_id, "m": members, "p": person_id})
    _system(graph, channel_id, f"{names.get(person_id)} left the group" if person_id == by_id
            else f"{names.get(by_id)} removed {names.get(person_id)}")
    return members


# ---------- messages ----------

MESSAGE_FIELDS = """m.id AS id, m.text AS text, m.author AS author, m.author_id AS author_id, m.ts AS ts, m.kind AS kind,
       m.sources AS sources, m.links AS links, m.reply_to AS reply_to, m.edited_at AS edited_at,
       coalesce(m.deleted, false) AS deleted, m.reactions AS reactions"""


def messages(graph: Graph, channel_id: str, after: str | None = None, limit: int = 300) -> list[dict]:
    """Messages in time order. With `after`, only messages sent or changed (edited, deleted, reacted to) since then."""
    found = rows(graph, f"""
        MATCH (m)-[:PART_OF]->(:Source {{id:$ch}})
        WHERE (m:Chunk OR m:Message) AND ($after IS NULL OR m.ts > $after OR coalesce(m.changed_at, '') > $after)
        OPTIONAL MATCH (m)-[:MENTIONS|REFERS_TO]->(x) WHERE NOT x:Source
        RETURN {MESSAGE_FIELDS},
               collect(DISTINCT {{id: x.id, label: labels(x)[0], name: coalesce(x.name, x.id)}}) AS about
        ORDER BY ts DESC LIMIT $limit
    """, {"ch": channel_id, "after": after, "limit": limit})
    found.reverse()
    replies = {m["reply_to"] for m in found if m["reply_to"]}
    quoted = {r["id"]: r for r in rows(graph, """
        MATCH (r)-[:PART_OF]->(:Source {id:$ch}) WHERE (r:Chunk OR r:Message) AND r.id IN $ids
        RETURN r.id AS id, r.author AS author, r.text AS text, coalesce(r.deleted, false) AS deleted""",
        {"ch": channel_id, "ids": sorted(replies)})} if replies else {}
    for m in found:
        m["reactions"] = json.loads(m["reactions"]) if m["reactions"] else {}
        if m["deleted"]:
            m.update(text="", about=[], links=None, sources=None)
        q = quoted.get(m["reply_to"]) if m["reply_to"] else None
        m["reply"] = None if not m["reply_to"] else (
            {"id": m["reply_to"], "author": q["author"], "text": "" if q["deleted"] else (q["text"] or "")[:200],
             "deleted": q["deleted"]} if q else {"id": m["reply_to"], "author": None, "text": "", "deleted": True})
    return found


def post(graph: Graph, channel_id: str, text: str, author: str, author_id: str | None, kind: str = "message",
         sources: list[str] | None = None, links: list[dict] | None = None, reply_to: str | None = None) -> dict:
    """Store one message and link it to what it names.

    Channel messages become company knowledge: `Chunk` passages that search, "who knows" and timelines use.
    Direct and group messages stay private by construction: they are `Message` nodes that no knowledge query matches.
    """
    ts = _now()
    mid = f"{channel_id}#" + hashlib.sha256(f"{author}|{ts}|{text}".encode()).hexdigest()[:10]
    ch = rows(graph, "MATCH (c:Channel {id:$id}) RETURN c.name AS name, c.kind AS kind", {"id": channel_id})
    private = bool(ch) and ch[0]["kind"] in PRIVATE
    title = "Neura1 Chat (private)" if private else f"Neura1 Chat #{ch[0]['name'] if ch else channel_id}"
    label, link = ("Message", "REFERS_TO") if private else ("Chunk", "MENTIONS")
    graph.query(f"""
        MERGE (s:Source {{id:$sid}}) ON CREATE SET s.kind=$skind, s.title=$title, s.authority='source_document',
                                                 s.uri=$sid, s.first_seen=$ts
        SET s.updated_at=$ts
        CREATE (m:{label} {{id:$mid, text:$text, author:$author, author_id:$aid, ts:$ts, kind:$kind,
                         source_version:'live', text_hash:$hash, ordinal:0, sources:$sources, links:$links,
                         reply_to:$reply}})
        CREATE (m)-[:PART_OF]->(s)
        WITH m OPTIONAL MATCH (p:Person {{id:$aid}})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (m)-[:SAID_BY]->(p))
    """, {"sid": channel_id, "skind": "dm" if private else "chat", "title": title, "mid": mid, "text": text,
          "author": author, "aid": author_id, "ts": ts, "kind": kind, "hash": hashlib.sha256(text.encode()).hexdigest()[:12],
          "sources": json.dumps(sources or []), "links": json.dumps(links or []), "reply": reply_to})
    targets = _link(graph, mid, label, link, text, channel_id) if kind != "system" else []
    if not private and kind != "system":
        _embed_later(graph, mid, text)
    if author_id:
        stop_typing(channel_id, author_id)
        mark_read(graph, channel_id, author_id, ts)
    return {"id": mid, "ts": ts, "about": targets}


def _system(graph: Graph, channel_id: str, text: str) -> None:
    post(graph, channel_id, text, BOT, None, kind="system")


def _link(graph: Graph, mid: str, label: str, link: str, text: str, channel_id: str) -> list[str]:
    targets = sorted(mentions(text, entity_lexicon(graph)) - {channel_id})
    if targets:
        graph.query(f"MATCH (m:{label} {{id:$mid}}) UNWIND $t AS tid MATCH (x {{id:tid}}) MERGE (m)-[:{link}]->(x)",
                    {"mid": mid, "t": targets})
    return targets


def _embed_later(graph: Graph, mid: str, text: str) -> None:
    def work():
        try:
            from neura1.llm import embed
            v = embed([text])[0]
            graph.query("MATCH (m:Chunk {id:$id}) WHERE NOT coalesce(m.deleted, false) SET m.embedding = vecf32($v)",
                        {"id": mid, "v": v})
        except Exception:
            pass  # semantic search simply will not see this message; keyword search and links still do
    threading.Thread(target=work, daemon=True).start()


def _own_message(graph: Graph, message_id: str, person_id: str) -> tuple[dict, str]:
    channel_id = message_id.split("#", 1)[0]
    found = rows(graph, """MATCH (m)-[:PART_OF]->(:Source {id:$ch}) WHERE (m:Chunk OR m:Message) AND m.id = $id
                           RETURN m.author_id AS author_id, coalesce(m.deleted, false) AS deleted,
                                  m.reactions AS reactions, labels(m)[0] AS label""",
                 {"ch": channel_id, "id": message_id})
    if not found:
        raise ChatError(404, "Unknown message")
    return found[0], channel_id


def edit_message(graph: Graph, message_id: str, person_id: str, text: str) -> dict:
    m, channel_id = _own_message(graph, message_id, person_id)
    text = text.strip()
    if m["author_id"] != person_id:
        raise ChatError(403, "You can only edit your own messages")
    if m["deleted"]:
        raise ChatError(400, "This message was deleted")
    if not text or len(text) > MAX_TEXT:
        raise ChatError(400, "Message is empty or too long")
    label = m["label"]
    link = "REFERS_TO" if label == "Message" else "MENTIONS"
    now = _now()
    graph.query(f"""MATCH (m:{label} {{id:$id}}) SET m.text=$t, m.text_hash=$h, m.edited_at=$now, m.changed_at=$now
                    WITH m OPTIONAL MATCH (m)-[r:{link}]->() DELETE r""",
                {"id": message_id, "t": text, "h": hashlib.sha256(text.encode()).hexdigest()[:12], "now": now})
    about = _link(graph, message_id, label, link, text, channel_id)
    if label == "Chunk":
        graph.query("MATCH (m:Chunk {id:$id}) SET m.embedding = NULL", {"id": message_id})
        _embed_later(graph, message_id, text)
    return {"id": message_id, "edited_at": now, "about": about}


def delete_message(graph: Graph, message_id: str, person_id: str) -> dict:
    """Delete for everyone: the text and its links leave the graph; a placeholder keeps the conversation readable."""
    m, _ = _own_message(graph, message_id, person_id)
    if m["author_id"] != person_id:
        raise ChatError(403, "You can only delete your own messages")
    label = m["label"]
    now = _now()
    graph.query(f"""MATCH (m:{label} {{id:$id}})
                    SET m.text='', m.deleted=true, m.retracted_at=$now, m.changed_at=$now, m.embedding=NULL,
                        m.reactions=NULL, m.links=NULL, m.sources=NULL
                    WITH m OPTIONAL MATCH (m)-[r:MENTIONS|REFERS_TO]->() DELETE r""", {"id": message_id, "now": now})
    return {"id": message_id, "deleted": True}


def react(graph: Graph, message_id: str, person_id: str, emoji: str) -> dict:
    """Toggle one emoji reaction by this person."""
    if emoji not in REACTIONS:
        raise ChatError(400, "Unknown reaction")
    m, _ = _own_message(graph, message_id, person_id)
    if m["deleted"]:
        raise ChatError(400, "This message was deleted")
    current: dict[str, list[str]] = json.loads(m["reactions"]) if m["reactions"] else {}
    who = set(current.get(emoji, []))
    who.symmetric_difference_update({person_id})
    if who:
        current[emoji] = sorted(who)
    else:
        current.pop(emoji, None)
    graph.query(f"MATCH (m:{m['label']} {{id:$id}}) SET m.reactions=$r, m.changed_at=$now",
                {"id": message_id, "r": json.dumps(current, ensure_ascii=False) if current else None, "now": _now()})
    return {"id": message_id, "reactions": current}


def mark_read(graph: Graph, channel_id: str, person_id: str, ts: str | None = None) -> None:
    """Remember the newest message this person has seen here (never moves backwards)."""
    ts = ts or _now()
    graph.query("""MATCH (p:Person {id:$p}), (c:Channel {id:$c})
                   MERGE (p)-[r:READ_UP_TO]->(c)
                   SET r.ts = CASE WHEN coalesce(r.ts, '') > $ts THEN r.ts ELSE $ts END""",
                {"p": person_id, "c": channel_id, "ts": ts})


def read_state(graph: Graph, channel_id: str) -> dict[str, str]:
    """How far each member has read, for read receipts in direct messages and groups."""
    return {r["p"]: r["ts"] for r in rows(graph, """MATCH (p:Person)-[r:READ_UP_TO]->(:Channel {id:$c})
                                                    RETURN p.id AS p, r.ts AS ts""", {"c": channel_id})}


def search(graph: Graph, viewer: "access.Viewer", text: str, limit: int = 40) -> list[dict]:
    """Messages containing the text, in conversations this viewer can read."""
    text = text.strip()
    if len(text) < 2:
        return []
    allowed = [c for c in channels(graph, viewer.id, viewer.name)
               if viewer.sees_money or c["id"] not in MONEY_CHANNELS]
    names = {c["id"]: c["name"] for c in allowed}
    found = rows(graph, f"""
        MATCH (m)-[:PART_OF]->(s:Source) WHERE s.id IN $ids AND (m:Chunk OR m:Message)
          AND NOT coalesce(m.deleted, false) AND coalesce(m.kind, '') <> 'system' AND toLower(m.text) CONTAINS $q
        RETURN s.id AS channel, {MESSAGE_FIELDS} ORDER BY ts DESC LIMIT $n""",
                 {"ids": list(names), "q": text.lower(), "n": limit})
    return [f | {"channel_name": names.get(f["channel"]), "kind_of_channel": next(c["kind"] for c in allowed if c["id"] == f["channel"])}
            for f in found]


# ---------- presence and typing ----------

def _online(person_id: str) -> bool:
    return time.time() - _seen.get(person_id, 0) < 60


def seen(person_id: str | None) -> None:
    if person_id:
        _seen[person_id] = time.time()


def typing(channel_id: str, person_id: str, name: str) -> None:
    with _lock:
        _typing.setdefault(channel_id, {})[person_id] = (name, time.time())


def stop_typing(channel_id: str, person_id: str) -> None:
    with _lock:
        _typing.get(channel_id, {}).pop(person_id, None)


def who_is_typing(channel_id: str, except_id: str | None) -> list[str]:
    now = time.time()
    with _lock:
        live = {p: v for p, v in _typing.get(channel_id, {}).items() if now - v[1] < 6}
        _typing[channel_id] = live
    return [name for p, (name, _) in live.items() if p != except_id]


def recent_cursor() -> str:
    """Where the next poll starts. A little overlap keeps a message written during this poll from being missed."""
    return (datetime.now(timezone.utc) - timedelta(seconds=3)).isoformat(timespec="microseconds")


# ---------- commands, answered from the graph without a model ----------

HELP = ("Try: `/impact NB54360 320 22` (price and lead time are optional), `/slips` (what is late against the plan), "
        "`/who CAN bus`, `/away Raghavendra`, `/risk`, or ask anything with `@neura1`.")


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
            lines.append("Cost figures are visible in #leadership.")
        if risk:
            lines.append(f"{len(risk)} builds at risk; orders exposed: {', '.join(o['order'] + ' ' + o['customer'] for o in orders)}.")
        if rejected:
            lines.append(f"Do not switch to {', '.join(rejected)}: rejected before (see decisions).")
        lines.append(f"{len(r['actions'])} tasks proposed under HB-ENG-04.")
        q = f"item={r['part']['id']}" + (f"&price={price}" if price else "") + (f"&lead={lead}" if lead else "")
        return {"text": " ".join(lines), "links": [{"label": "Open impact", "href": f"/impact?{q}"}]}
    if cmd in ("/slips", "/timeline"):
        from neura1.agent import Reader, plan_deviations
        reader = Reader(None if audience is None else {"money": audience.money, "leave_of": audience.sees_leave_of})
        r = plan_deviations(graph, reader, " ".join(args) or None, limit=5)
        s = r["summary"]
        lines = [f"{s['late']} item{'s' if s['late'] != 1 else ''} late, {s['projects_past_target']} project"
                 f"{'s' if s['projects_past_target'] != 1 else ''} past target."]
        for p in r["projects"]:
            if (p["days_late"] or 0) > 0:
                lines.append(f"**{p['name']}**: target {p['target']}, forecast {p['forecast']} (+{p['days_late']} days).")
        for i in r["slipping"]:
            if i["state"] == "late":
                lines.append(f"`{i['id']}` +{i['days_late']} days: {(i['why'] or [''])[0]}")
        return {"text": " ".join(lines), "links": [{"label": "Open the timeline", "href": "/timeline"}]}
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
                             f"backup and the leadership team on the handover page."),
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

def ask_in_channel(graph: Graph, channel_id: str, question: str, asker_id: str | None,
                   reply_to: str | None = None) -> None:
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
                            "MATCH (v:Conversation {id:$cid}) SET v.private = (c.kind IN ['dm', 'group'])",
                            {"id": channel_id, "cid": cid})
            audience = Audience(graph, channel_id)
            result = agent.ask(graph, question, history=memory.history(graph, cid),
                               restrict={"money": audience.money, "leave_of": audience.sees_leave_of,
                                         "hidden": access.hidden_sources(graph, audience.sees_leave_of)})
            memory.record(graph, cid, question, result)
            text = redact_text(result["answer"], audience)
            if result.get("warnings"):
                text += "\n\n" + "\n".join(result["warnings"])
            post(graph, channel_id, text, BOT, None, kind="answer", sources=result.get("sources", []), reply_to=reply_to)
        except Exception as exc:
            post(graph, channel_id, f"I could not answer that right now ({exc}). Graph commands like /impact still work.",
                 BOT, None, kind="error", reply_to=reply_to)

    threading.Thread(target=work, daemon=True).start()


def handle(graph: Graph, channel_id: str, text: str, author: str, author_id: str | None,
           reply_to: str | None = None) -> dict:
    msg = post(graph, channel_id, text, author, author_id, reply_to=reply_to)
    stripped = text.strip()
    if author_id and not stripped.startswith("/"):
        _remind(graph, channel_id, stripped, msg["id"])
    if stripped.startswith("/"):
        reply = command(graph, stripped, Audience(graph, channel_id))
        post(graph, channel_id, reply["text"], BOT, None, kind="command", links=reply.get("links"), reply_to=msg["id"])
    elif re.search(r"@neura1\b", text, re.I) or _is_bot_channel(graph, channel_id):
        ask_in_channel(graph, channel_id, re.sub(r"@neura1\b", "", text, flags=re.I).strip(), author_id, msg["id"])
        msg["thinking"] = True
    return msg


def _is_bot_channel(graph: Graph, channel_id: str) -> bool:
    ch = rows(graph, "MATCH (c:Channel {id:$id}) RETURN c.kind AS kind", {"id": channel_id})
    return bool(ch) and ch[0]["kind"] == "bot"


def _remind(graph: Graph, channel_id: str, text: str, message_id: str) -> None:
    """If a message proposes something the company already rejected, answer it with the decision and its proof."""
    from neura1 import guard
    try:
        note = guard.reminder(guard.check(graph, text, access.Viewer()))
    except Exception:
        return  # a reminder must never stop a message from being sent
    if note:
        post(graph, channel_id, redact_text(note, Audience(graph, channel_id)), BOT, None, kind="guard",
             reply_to=message_id)


# ---------- Neura1 speaks first ----------

def notify(graph: Graph, kind: str, text: str, links: list[dict] | None = None) -> None:
    """Post a proactive message to the channel that should know about this kind of event."""
    try:
        ensure_channels(graph)
        post(graph, f"chat/{ROUTES.get(kind, 'general')}", text, BOT, None, kind="notice", links=links)
    except Exception:
        pass  # a failed notification must never break the action that triggered it
