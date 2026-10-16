"""Live ingestion from Slack (Events API) and Jira (webhooks), in their real payload formats.

Each message or ticket change becomes a passage in the graph immediately: linked to the people, parts, orders and
projects it names, and visible in What's new, search, who-knows and the agent. Nothing is invented: if a payload is
not a message or ticket event, it is ignored.
"""

import hashlib
import hmac
import time
from datetime import datetime, timezone

from falkordb import Graph

from neura1.ingest.unstructured import entity_lexicon, mentions


def verify_slack(signing_secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    """Slack's v0 request signing: HMAC-SHA256 of 'v0:{timestamp}:{body}', rejected if older than 5 minutes."""
    if not timestamp or abs(time.time() - int(timestamp)) > 300:
        return False
    base = f"v0:{timestamp}:".encode() + body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _iso(ts: str | float | None) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return str(ts) if ts else datetime.now(timezone.utc).isoformat(timespec="seconds")


def _passage(graph: Graph, source: dict, key: str, text: str, author: str | None, ts: str) -> str:
    cid = f"{source['id']}#{key}"
    graph.query("""
        MERGE (s:Source {id:$s.id})
        ON CREATE SET s.first_seen=$now
        SET s += $s, s.authority='source_document', s.updated_at=$now
        MERGE (c:Chunk {id:$cid}) ON CREATE SET c.first_seen=$now
        SET c.text=$text, c.author=$author, c.ts=$ts, c.source_version='live',
            c.text_hash=$hash, c.ordinal=coalesce(c.ordinal, 0)
        MERGE (c)-[:PART_OF]->(s)
        WITH c OPTIONAL MATCH (c)-[old:SAID_BY|MENTIONS]->() DELETE old
        WITH DISTINCT c OPTIONAL MATCH (p:Person {name:$author})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (c)-[:SAID_BY]->(p))
    """, {"s": source, "cid": cid, "text": text, "author": author, "ts": ts,
          "hash": hashlib.sha256(text.encode()).hexdigest()[:12], "now": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    targets = sorted(mentions(text, entity_lexicon(graph)) - {source["id"]})
    if targets:
        graph.query("MATCH (c:Chunk {id:$cid}) UNWIND $t AS tid MATCH (x {id:tid}) MERGE (c)-[:MENTIONS]->(x)",
                    {"cid": cid, "t": targets})
    return cid


def slack_event(graph: Graph, payload: dict) -> dict:
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}
    event = payload.get("event") or {}
    if payload.get("type") != "event_callback" or event.get("type") != "message" or event.get("subtype"):
        return {"ignored": True}
    channel = event.get("channel_name") or event.get("channel") or "unknown"
    author = (event.get("user_profile") or {}).get("real_name") or event.get("user_name") or event.get("user")
    source = {"id": f"live/slack/{channel}", "kind": "chat", "title": f"Slack #{channel}", "uri": f"slack:{channel}"}
    cid = _passage(graph, source, str(event.get("client_msg_id") or event.get("ts")), event.get("text", ""),
                   author, _iso(event.get("ts")))
    return {"ingested": cid}


def jira_event(graph: Graph, payload: dict) -> dict:
    kind = payload.get("webhookEvent", "")
    issue = payload.get("issue") or {}
    fields = issue.get("fields") or {}
    key = issue.get("key")
    if not key or not kind.startswith(("jira:issue", "comment_")):
        return {"ignored": True}
    assignee = (fields.get("assignee") or {}).get("displayName")
    source = {"id": f"live/jira/{key}", "kind": "ticket", "title": f"{key}: {fields.get('summary', '')}", "ref": key,
              "status": (fields.get("status") or {}).get("name"), "assignee": assignee, "uri": f"jira:{key}"}
    ingested = [_passage(graph, source, "description", fields.get("description") or fields.get("summary", ""),
                         (fields.get("reporter") or {}).get("displayName"), _iso(time.time()))]
    comment = payload.get("comment")
    if comment:
        ingested.append(_passage(graph, source, f"comment-{comment.get('id', len(ingested))}", comment.get("body", ""),
                                 (comment.get("author") or {}).get("displayName"), comment.get("created") or _iso(time.time())))
    if assignee:
        graph.query("""MATCH (s:Source {id:$sid}) OPTIONAL MATCH (s)-[old:ASSIGNED_TO]->() DELETE old
                       WITH DISTINCT s MATCH (p:Person {name:$who}) MERGE (s)-[:ASSIGNED_TO]->(p)""",
                    {"sid": source["id"], "who": assignee})
    return {"ingested": ingested, "status": source["status"]}
