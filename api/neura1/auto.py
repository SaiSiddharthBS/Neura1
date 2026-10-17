"""The DGX worker: new information is read as it arrives, without anyone running a command.

Every 30 seconds, while the main model (the DGX) is reachable:
- **Live sources** whose content changed since they were last read (Slack and Jira webhooks, imported and saved
  documents, Neura1 Chat channels, forwarded escalations) are read for decisions, and meeting notes for action items.
  Everything goes through the same word-for-word verification as the fixture; verified decisions are announced.
- **New tasks** (from plans, Ask drafts or the workboard) are tagged with the skills they need, from Flyvi's list only.

The fixture's own documents are not re-read: their extractions are snapshots, loaded by `cli load`. Live snapshots are
kept under data/extracted/. Nothing runs on the fallback model, so a laptop is never asked to do the DGX's work.
"""

import threading
import time
from datetime import datetime, timezone

from falkordb import Graph

from neura1.config import settings
from neura1.graph import rows

READ_KINDS = ["chat", "ticket", "doc", "document", "escalation", "leave"]
MEETING = ("weekly", "review", "kickoff", "minutes", "meeting", "standup", "sync")
QUIET_SECONDS = 45      # a chat channel is read once it has been quiet this long, so a conversation is read whole
MAX_PASSAGES = 60       # the newest passages of a busy channel


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stale_sources(graph: Graph) -> list[dict]:
    """Live sources with content the model has not read yet, oldest change first.

    Documents and tickets are compared by content version. A chat channel counts as unread when a person (not Neura1)
    has written after the newest message already read, so Neura1's own posts never make a channel look new."""
    from neura1.chat import BOT

    docs = rows(graph, """
        MATCH (s:Source) WHERE s.kind IN $kinds AND s.kind <> 'chat'
          AND coalesce(s.extracted_version, '') <> coalesce(s.version, s.updated_at, '')
        RETURN s.id AS id, s.kind AS kind, s.title AS title, coalesce(s.version, s.updated_at, '') AS version,
               s.updated_at AS updated_at""", {"kinds": READ_KINDS})
    chats = rows(graph, """
        MATCH (s:Source {kind:'chat'})<-[:PART_OF]-(c:Chunk) WHERE coalesce(c.author, '') <> $bot AND c.ts IS NOT NULL
        WITH s, max(c.ts) AS last WHERE last > coalesce(s.read_until, '')
        RETURN s.id AS id, s.kind AS kind, s.title AS title, last AS version, last AS updated_at""", {"bot": BOT})
    live = []
    for src in sorted(docs + chats, key=lambda x: x["updated_at"] or ""):
        if (settings.fixture_dir / src["id"]).is_file():
            continue  # the fixture's documents come from saved snapshots
        if src["kind"] == "chat":
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(src["updated_at"])).total_seconds()
            except (TypeError, ValueError):
                age = QUIET_SECONDS
            if age < QUIET_SECONDS:
                continue  # wait until the conversation pauses, so it is read whole
        live.append(src)
    return live


def read_source(graph: Graph, src: dict) -> dict:
    """Extract and verify decisions (and meeting actions) from one live source, then mark it read."""
    from neura1 import chat
    from neura1.ingest import extract

    passages = extract.source_passages(graph, src["id"])
    if src["kind"] == "chat":  # people's messages only: Neura1 does not mine its own replies for decisions
        passages = [p for p in passages if p.get("author") != chat.BOT][-MAX_PASSAGES:]
    result: dict = {"source": src["id"], "decisions": [], "actions": []}
    known = {r["id"] for r in rows(graph, "MATCH (d:Decision) RETURN d.id AS id")}
    if passages:
        snap = extract.run_model(graph, src["id"], "decisions", passages)
        loaded = extract.load_decisions(graph, snap)
        result["decisions"] = [d for d in loaded["written"] if d not in known]  # only announce what is new
        result["rejected"] = loaded["rejected"]
        if src["kind"] in ("doc", "document") and any(w in (src.get("title") or "").lower() for w in MEETING):
            snap = extract.run_model(graph, src["id"], "actions", passages)
            result["actions"] = extract.load_action_items(graph, snap)["written"]
    mark = "s.read_until = $v" if src["kind"] == "chat" else "s.extracted_version = $v"
    graph.query(f"MATCH (s:Source {{id:$id}}) SET {mark}, s.extracted_at = $at", {"id": src["id"], "v": src["version"], "at": _now()})
    if result["decisions"]:
        summaries = rows(graph, "MATCH (d:Decision) WHERE d.id IN $ids RETURN d.id AS id, d.outcome AS o, d.summary AS s",
                         {"ids": result["decisions"]})
        text = "; ".join(f"{d['id']} ({d['o']}): {d['s']}" for d in summaries[:3])
        chat.notify(graph, "evidence", f"Neura1 read {src.get('title') or src['id']} and recorded "
                    f"{len(summaries)} decision{'s' if len(summaries) != 1 else ''}, each checked word for word: {text}.",
                    [{"label": "Explore", "href": f"/explore?id={summaries[0]['id']}"}] if summaries else None)
    return result


def tag_new_tasks(graph: Graph, batch: int = 12) -> int:
    """Tag tasks that have no skills yet with the skills they need (Flyvi's list only, verified by code)."""
    from neura1 import capabilities
    from neura1.llm import chat_json

    todo = rows(graph, """
        MATCH (a:Action) WHERE a.skills_tagged_at IS NULL AND NOT (a)-[:NEEDS_SKILL]->(:Skill)
        OPTIONAL MATCH (a)-[:IN_PROJECT]->(p:Project)
        RETURN a.id AS id, a.title + coalesce(' (project: ' + p.name + ')', '') + coalesce(' about ' + a.target, '') AS text
        ORDER BY id LIMIT $n""", {"n": batch})
    if not todo:
        return 0
    vocabulary = capabilities.skill_vocabulary(graph)
    user = "SKILLS:\n" + "\n".join(f"- {v}" for v in vocabulary) + "\n\nRECORDS:\n" + \
           "\n".join(f"[{t['id']}] {t['text']}" for t in todo)
    raw = chat_json(capabilities.TAG_SYSTEM, user, capabilities.TAG_SCHEMA, "skill_tags").get("tags", [])
    kept, _ = capabilities.verify_tags(raw, vocabulary, {t["id"] for t in todo})
    from neura1 import llm
    for t in todo:
        for skill in kept.get(t["id"], []):
            graph.query("""MATCH (a:Action {id:$id}), (s:Skill {name:$s})
                           MERGE (a)-[r:NEEDS_SKILL]->(s) SET r.by = 'model', r.model = $m, r.authority = 'extracted'""",
                        {"id": t["id"], "s": skill, "m": llm.last_model})
        graph.query("MATCH (a:Action {id:$id}) SET a.skills_tagged_at = $at", {"id": t["id"], "at": _now()})
    return len(todo)


def run_once(graph: Graph) -> dict:
    """One pass of the worker. Skipped entirely when the main model is not reachable."""
    from neura1 import llm

    if llm.status().get("on_fallback"):
        return {"skipped": "main model not reachable"}
    done = {"tagged": tag_new_tasks(graph), "read": []}
    for src in stale_sources(graph)[:3]:
        try:
            done["read"].append(read_source(graph, src))
        except Exception as exc:  # one bad source must not stop the worker; it is retried next pass
            done["read"].append({"source": src["id"], "error": str(exc)})
    return done


_started = False
last_run: dict = {}


def start(get_graph, every: float = 30.0) -> None:
    global _started
    if _started:
        return
    _started = True

    def loop():
        while True:
            try:
                last_run.clear()
                last_run.update(run_once(get_graph()) | {"at": _now()})
            except Exception as exc:
                last_run.update(error=str(exc), at=_now())
            time.sleep(every)

    threading.Thread(target=loop, daemon=True, name="neura1-dgx-worker").start()
