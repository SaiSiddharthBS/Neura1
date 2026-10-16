"""Conversation memory in the graph (Track 02).

Each question and answer is a Turn in a Conversation started by a Person. Turns link to the passages they cited and
to the records they were about, so memory is queryable like everything else: "what have we discussed about
NB54360?", by any user or any agent connected through MCP.
"""

import hashlib
import json
from datetime import datetime, timezone

from falkordb import Graph

from neura1.graph import rows
from neura1.ingest.unstructured import entity_lexicon, mentions


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start(graph: Graph, person_id: str | None, first_question: str) -> str:
    cid = "CONV-" + hashlib.sha256(f"{person_id}|{first_question}|{_now()}".encode()).hexdigest()[:10]
    graph.query("""
        CREATE (c:Conversation {id:$id, title:$title, started_at:$now})
        WITH c OPTIONAL MATCH (p:Person {id:$pid})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (p)-[:STARTED]->(c))
    """, {"id": cid, "title": first_question[:80], "now": _now(), "pid": person_id})
    return cid


def history(graph: Graph, conversation_id: str, limit: int = 4) -> list[dict]:
    turns = rows(graph, """
        MATCH (:Conversation {id:$id})-[:HAS_TURN]->(t:Turn)
        RETURN t.i AS i, t.question AS question, t.answer AS answer ORDER BY i DESC LIMIT $n
    """, {"id": conversation_id, "n": limit})
    return list(reversed(turns))


def record(graph: Graph, conversation_id: str, question: str, result: dict) -> dict:
    n = rows(graph, "MATCH (:Conversation {id:$id})-[:HAS_TURN]->(t:Turn) RETURN count(t) AS n",
             {"id": conversation_id})[0]["n"]
    about = sorted(mentions(question + "\n" + result.get("answer", ""), entity_lexicon(graph)))
    graph.query("""
        MATCH (c:Conversation {id:$cid})
        CREATE (t:Turn {i:$i, question:$q, answer:$a, at:$now, tools:$tools})
        CREATE (c)-[:HAS_TURN]->(t)
        WITH t UNWIND (CASE WHEN size($sources) = 0 THEN [NULL] ELSE $sources END) AS sid
        OPTIONAL MATCH (ch:Chunk {id:sid})
        FOREACH (_ IN CASE WHEN ch IS NULL THEN [] ELSE [1] END | MERGE (t)-[:CITED]->(ch))
        WITH DISTINCT t UNWIND (CASE WHEN size($about) = 0 THEN [NULL] ELSE $about END) AS xid
        OPTIONAL MATCH (x {id:xid}) WHERE NOT x:Turn
        FOREACH (_ IN CASE WHEN x IS NULL THEN [] ELSE [1] END | MERGE (t)-[:ABOUT]->(x))
    """, {"cid": conversation_id, "i": n + 1, "q": question, "a": result.get("answer", ""), "now": _now(),
          "tools": json.dumps(result.get("tool_calls", [])), "sources": result.get("sources", []), "about": about})
    return {"conversation_id": conversation_id, "turn": n + 1, "about": about}


def conversations(graph: Graph, person_id: str | None) -> list[dict]:
    return rows(graph, """
        MATCH (p:Person {id:$pid})-[:STARTED]->(c:Conversation)
        OPTIONAL MATCH (c)-[:HAS_TURN]->(t:Turn)
        RETURN c.id AS id, c.title AS title, c.started_at AS started_at, count(t) AS turns
        ORDER BY started_at DESC LIMIT 20
    """, {"pid": person_id})


def transcript(graph: Graph, conversation_id: str) -> list[dict]:
    return rows(graph, """
        MATCH (:Conversation {id:$id})-[:HAS_TURN]->(t:Turn)
        OPTIONAL MATCH (t)-[:CITED]->(ch:Chunk)
        RETURN t.i AS i, t.question AS question, t.answer AS answer, t.at AS at, t.tools AS tools,
               collect(ch.id) AS sources
        ORDER BY i
    """, {"id": conversation_id})


# Past turns about a record or matching words, across everyone's conversations (shared memory).
RECALL = """
MATCH (t:Turn)-[:ABOUT]->(x) WHERE x.id = $text OR toLower(coalesce(x.name, '')) = toLower($text)
MATCH (c:Conversation)-[:HAS_TURN]->(t) WHERE NOT coalesce(c.private, false)
OPTIONAL MATCH (p:Person)-[:STARTED]->(c)
RETURN t.question AS question, t.answer AS answer, t.at AS at, p.name AS asked_by
ORDER BY at DESC LIMIT 5
"""


def recall(graph: Graph, text: str) -> list[dict]:
    found = rows(graph, RECALL, {"text": text.strip()})
    if found:
        return found
    words = [w.lower() for w in text.split() if len(w) > 3]
    if not words:
        return []
    return rows(graph, """
        MATCH (c:Conversation)-[:HAS_TURN]->(t:Turn)
        WHERE NOT coalesce(c.private, false) AND any(w IN $words WHERE toLower(t.question) CONTAINS w)
        OPTIONAL MATCH (p:Person)-[:STARTED]->(c)
        RETURN t.question AS question, t.answer AS answer, t.at AS at, p.name AS asked_by
        ORDER BY at DESC LIMIT 5
    """, {"words": words})
