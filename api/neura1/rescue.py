"""Knowledge rescue: before someone leaves or goes on long leave, capture what only they know.

The questions come from the graph, by code: what the person owns, the subjects the company relies on them for most,
the decisions they were part of, and what depends on their work. The person answers in their own words. Each answer
becomes a passage of company knowledge (a `Chunk` of a `rescue/<person>` source), linked to what it talks about, so
search, Ask and "who knows" find it the day they are gone.

The model (the DGX) helps in two places only, and both are checked:
  * a follow-up question, when an answer is thin;
  * the facts Neura1 took from an answer, each kept only if its quote appears word for word in the answer.
"""

import hashlib
import json
import re
import threading
from datetime import datetime, timezone

from falkordb import Graph

from neura1 import scenarios
from neura1.graph import rows
from neura1.ingest.unstructured import entity_lexicon, mentions

DEPENDS = """
MATCH (:Person {id:$id})-[:OWNS]->(x:Item)-[d:DEPENDS_ON]->(p:Item)
RETURN x.id AS id, x.name AS name, p.id AS on, d.note AS note
"""

CAPTURED = """
MATCH (c:Chunk)-[:PART_OF]->(:Source {id:$src})
OPTIONAL MATCH (c)-[:MENTIONS]->(x)
RETURN c.id AS id, c.question AS question, c.question_id AS question_id, c.text AS text, c.ts AS ts,
       collect(DISTINCT x.id) AS about
ORDER BY ts
"""

FOLLOW_SYSTEM = """You help capture what one engineer knows before they leave, at an Indian maker of power and control
electronics. Given a question and the person's answer, do two things:
1. "facts": the concrete facts in the answer that a successor needs (values, steps, gotchas, people or suppliers to call).
   Each fact has a short "statement" and the exact "quote" from the answer that supports it, copied word for word.
2. "followup": one short, specific follow-up question if something important is missing or vague (for example a value,
   a test step, or why). Return null if the answer is already complete. Never ask about anything personal.
Return JSON only."""

FOLLOW_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "items": {"type": "object", "properties": {
            "statement": {"type": "string"}, "quote": {"type": "string"}}, "required": ["statement", "quote"]}},
        "followup": {"type": ["string", "null"]},
    },
    "required": ["facts", "followup"],
}


def source_id(person_id: str) -> str:
    return f"rescue/{person_id}"


def plan(graph: Graph, person_id: str) -> dict:
    """The interview: questions from the graph, each with why it is asked, and what is already captured."""
    a = scenarios.absence_impact(graph, person_id)
    if a.get("status") == "unknown_person":
        return {"status": "unknown_person"}
    name = a["person"]["name"]
    qs: list[dict] = []

    def ask(qid, about, text, why):
        if qid not in {q["id"] for q in qs}:
            qs.append({"id": qid, "about": [x for x in about if x], "question": text, "why": why})

    risk = {k["id"]: k for k in a["knowledge_at_risk"]}
    for o in a["owned"]:
        k = risk.get(o["id"])
        ask(f"own:{o['id']}", [o["id"]],
            f"You own {o['name']}. What should the next owner know first: what tends to break, what is not written "
            f"down anywhere, and who to call (people or suppliers)?",
            f"{name} owns it" + (f"; {round(100 * k['share'])}% of what Flyvi knows about it sits with {name}" if k else ""))
    for d in rows(graph, DEPENDS, {"id": person_id}):
        ask(f"dep:{d['id']}", [d["id"], d["on"]],
            f"{d['name']} depends on {d['on']}: “{d['note']}”. If {d['on']} changes, what exactly has to be checked "
            f"in {d['id']}, and how would someone test it?",
            f"Recorded dependency of {d['id']} on {d['on']}")
    for k in a["knowledge_at_risk"][:4]:
        if k["id"] not in {o["id"] for o in a["owned"]}:
            ask(f"know:{k['id']}", [k["id"]],
                f"Flyvi relies on you more than anyone for {k['id']} ({', '.join(k['why'][:3])}). What would someone "
                f"need to know to change it safely?",
                f"{round(100 * k['share'])}% of the evidence about {k['id']} points to {name}; next best "
                f"{k['next_best'] or 'nobody'}")
    for d in a["decisions"][:3]:
        ask(f"dec:{d['id']}", [d["id"], d["subject"]],
            f"You were part of {d['id']}: {d['summary']}. What was the reasoning that is not in the record, and when "
            f"should it be revisited?",
            f"Decision {d['outcome']} with {name}")
    for pr in a["led_projects"]:
        ask(f"lead:{pr['id']}", [pr["id"]],
            f"You lead {pr['name']}. What would an interim lead need this week: open risks, promises made, and people "
            f"to keep close?",
            f"{name} leads it")
    captured = rows(graph, CAPTURED, {"src": source_id(person_id)})
    done = {c["question_id"] for c in captured}
    return {"status": "ok", "person": {"id": person_id, "name": name}, "absence": a["absence"],
            "questions": [q | {"answered": q["id"] in done} for q in qs[:8]],
            "captured": captured, "at_risk": a["knowledge_at_risk"][:6]}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def save(graph: Graph, person_id: str, question_id: str, question: str, about: list[str], answer: str,
         recorded_by: str | None) -> dict:
    """Store one answer as company knowledge, linked to what it is about and what it names."""
    who = rows(graph, "MATCH (p:Person {id:$id}) RETURN p.name AS name", {"id": person_id})
    if not who:
        raise ValueError("Unknown person")
    name = who[0]["name"]
    src = source_id(person_id)
    ts = _now()
    cid = f"{src}#" + hashlib.sha256(f"{question_id}|{ts}".encode()).hexdigest()[:10]
    graph.query("""
        MERGE (s:Source {id:$src}) ON CREATE SET s.kind='rescue', s.title=$title, s.authority='person_statement',
                                               s.uri=$src, s.first_seen=$ts
        SET s.updated_at=$ts
        CREATE (c:Chunk {id:$cid, text:$text, author:$name, author_id:$pid, ts:$ts, kind:'rescue', question:$q,
                         question_id:$qid, recorded_by:$by, source_version:'live', ordinal:0,
                         text_hash:$hash})
        CREATE (c)-[:PART_OF]->(s)
        WITH c MATCH (p:Person {id:$pid}) CREATE (c)-[:SAID_BY]->(p)
    """, {"src": src, "title": f"Knowledge captured from {name}", "ts": ts, "cid": cid, "text": answer.strip(),
          "name": name, "pid": person_id, "q": question, "qid": question_id, "by": recorded_by,
          "hash": hashlib.sha256(answer.encode()).hexdigest()[:12]})
    targets = sorted((set(about) | mentions(answer, entity_lexicon(graph))) - {person_id})
    if targets:
        graph.query("MATCH (c:Chunk {id:$cid}) UNWIND $t AS tid MATCH (x {id:tid}) MERGE (c)-[:MENTIONS]->(x)",
                    {"cid": cid, "t": targets})
    threading.Thread(target=_embed, args=(graph, cid, f"{question}\n{answer}"), daemon=True).start()
    return {"id": cid, "ts": ts, "about": targets}


def _embed(graph: Graph, cid: str, text: str) -> None:
    try:
        from neura1.llm import embed
        graph.query("MATCH (c:Chunk {id:$id}) SET c.embedding = vecf32($v)", {"id": cid, "v": embed([text])[0]})
    except Exception:
        pass  # keyword search and links still find it


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()


def review(question: str, answer: str) -> dict:
    """Facts taken from an answer (each verified word for word) and a follow-up question, from the main model."""
    from neura1 import llm
    if llm.status().get("on_fallback"):
        return {"facts": [], "followup": None, "model": None, "note": "The main model is not reachable"}
    try:
        out = llm.chat_json(FOLLOW_SYSTEM, f"QUESTION: {question}\n\nANSWER: {answer}", FOLLOW_SCHEMA, "rescue_review")
    except Exception as exc:
        return {"facts": [], "followup": None, "model": None, "note": f"Review unavailable ({exc})"}
    plain = _norm(answer)
    facts = [f for f in out.get("facts") or [] if f.get("quote") and _norm(f["quote"]) in plain]
    dropped = len(out.get("facts") or []) - len(facts)
    follow = out.get("followup")
    follow = follow.strip() if isinstance(follow, str) and follow.strip() and len(follow) < 300 else None
    return {"facts": facts[:6], "followup": follow, "dropped": dropped, "model": llm.last_model}


def coverage(graph: Graph, person_id: str) -> dict[str, int]:
    """How many captured answers talk about each subject (used to lower knowledge risk elsewhere)."""
    return {r["id"]: r["n"] for r in rows(graph, """
        MATCH (:Source {id:$src})<-[:PART_OF]-(c:Chunk)-[:MENTIONS]->(x) RETURN x.id AS id, count(c) AS n""",
        {"src": source_id(person_id)})}


def as_json(data) -> str:
    return json.dumps(data, ensure_ascii=False)
