"""Company-wide questions over the same graph: who knows what, people, projects, and what changed.

Everything here is a Cypher traversal plus simple scoring in Python. No model is involved, so the
answers are fast, repeatable, and every claim points at the records or passages behind it.
"""

from datetime import date, timedelta

from falkordb import Graph

from neura1.impact import Trace

# Anything a person might ask about, found by id, name, or an alias used in chats.
RESOLVE_ANY = """
MATCH (x)
WHERE (x:Item OR x:Revision OR x:Project OR x:Customer OR x:Order OR x:Build OR x:Person OR x:Team OR x:Supplier)
  AND (toUpper(x.id) = toUpper($text) OR toLower(x.name) = toLower($text) OR toUpper(x.mpn) = toUpper($text))
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.id) AS name
UNION
MATCH (a:Alias)-[:REFERS_TO]->(x) WHERE toLower(a.term) = toLower($text)
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.id) AS name
"""

# Who knows about a record, and why. Each branch is one kind of signal with a weight; the evidence
# column names the record or passage that supports it.
WHO_KNOWS = """
MATCH (p:Person)-[:OWNS]->(x {id:$id})
RETURN p.id AS person, 'owns it' AS signal, 5 AS weight, x.id AS evidence, NULL AS ts
UNION ALL
MATCH (p:Person)-[:LEADS]->(x:Project {id:$id})
RETURN p.id AS person, 'leads the project' AS signal, 5 AS weight, x.id AS evidence, NULL AS ts
UNION ALL
MATCH (p:Person)<-[:DECIDED_BY]-(d:Decision)-[:ABOUT]->(s:Item)
WHERE s.id = $id OR (s)-[:ALTERNATE_OF]-(:Item {id:$id})
RETURN p.id AS person, 'made a decision about it' AS signal, 4 AS weight, d.id AS evidence, d.decided_at AS ts
UNION ALL
MATCH (p:Person)-[:OWNS]->(a:Item)-[:HAS_REV]->(:Revision)-[:CONTAINS]->(x:Item {id:$id})
RETURN p.id AS person, 'owns an assembly that uses it' AS signal, 2 AS weight, a.id AS evidence, NULL AS ts
UNION ALL
MATCH (p:Person)-[:OWNS]->(d:Item)-[:DEPENDS_ON]->(x:Item {id:$id})
RETURN p.id AS person, 'owns something that depends on it' AS signal, 3 AS weight, d.id AS evidence, NULL AS ts
UNION ALL
MATCH (p:Person)-[w:WORKS_ON]->(pr:Project)-[:COVERS]->(x {id:$id})
RETURN p.id AS person, 'works on ' + pr.name AS signal, 2 AS weight, pr.id AS evidence, NULL AS ts
UNION ALL
MATCH (p:Person)-[:WORKS_ON]->(x:Project {id:$id})
RETURN p.id AS person, 'works on the project' AS signal, 3 AS weight, x.id AS evidence, NULL AS ts
UNION ALL
MATCH (p:Person)<-[:SAID_BY]-(c:Chunk)-[:MENTIONS]->(x {id:$id})
WHERE c.retracted_at IS NULL
RETURN p.id AS person, 'discussed it' AS signal, 1 AS weight, c.id AS evidence, c.ts AS ts
UNION ALL
MATCH (b:Person)-[:BACKS_UP]->(o:Person)-[:OWNS]->(x {id:$id})
RETURN b.id AS person, 'backs up the owner' AS signal, 2 AS weight, o.id AS evidence, NULL AS ts
"""

PERSON = """
MATCH (p:Person {id:$id})
OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p)
OPTIONAL MATCH (p)-[:BACKS_UP]->(covers:Person)
RETURN p.id AS id, p.name AS name, p.role AS role, t.name AS team,
       collect(DISTINCT b.name) AS backed_up_by, collect(DISTINCT covers.name) AS backs_up
"""

PERSON_OWNS = """
MATCH (:Person {id:$id})-[:OWNS]->(x)
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.id) AS name ORDER BY label, id
"""

PERSON_PROJECTS = """
MATCH (p:Person {id:$id})-[r:WORKS_ON|LEADS]->(pr:Project)
RETURN pr.id AS id, pr.name AS name, pr.status AS status, collect(DISTINCT coalesce(r.role, 'lead')) AS roles
ORDER BY id
"""

PERSON_DECISIONS = """
MATCH (:Person {id:$id})<-[:DECIDED_BY]-(d:Decision)-[:ABOUT]->(s:Item)
RETURN d.id AS id, d.outcome AS outcome, s.id AS subject, d.summary AS summary, d.decided_at AS decided_at
ORDER BY decided_at DESC
"""

PERSON_TASKS = """
MATCH (:Person {id:$id})<-[:ASSIGNED_TO]-(a:Action)
OPTIONAL MATCH (inv:Investigation)-[:PRODUCED]->(a)
RETURN a.id AS id, a.title AS title, a.status AS status, a.created_at AS created_at, inv.id AS investigation
ORDER BY created_at DESC
"""

# What a person talks about, from passages attributed to them: their working knowledge.
PERSON_TOPICS = """
MATCH (:Person {id:$id})<-[:SAID_BY]-(c:Chunk)-[:MENTIONS]->(x)
WHERE NOT x:Person AND NOT x:Source AND c.retracted_at IS NULL
RETURN x.id AS id, labels(x)[0] AS label, count(c) AS mentions, max(c.ts) AS last
ORDER BY mentions DESC LIMIT 12
"""

PERSON_RECENT = """
MATCH (:Person {id:$id})<-[:SAID_BY]-(c:Chunk)-[:PART_OF]->(s:Source)
WHERE c.retracted_at IS NULL
RETURN c.id AS chunk, c.text AS text, c.ts AS ts, s.title AS title ORDER BY ts DESC LIMIT 6
"""

PEOPLE = """
MATCH (p:Person)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (p)-[:OWNS]->(x)
OPTIONAL MATCH (p)-[:WORKS_ON|LEADS]->(pr:Project)
RETURN p.id AS id, p.name AS name, p.role AS role, t.name AS team,
       count(DISTINCT x) AS owns, collect(DISTINCT pr.id) AS projects
ORDER BY team, name
"""

PROJECTS = """
MATCH (pr:Project)
OPTIONAL MATCH (lead:Person)-[:LEADS]->(pr)
OPTIONAL MATCH (m:Person)-[:WORKS_ON]->(pr)
OPTIONAL MATCH (pr)-[:COVERS]->(x)
RETURN pr.id AS id, pr.name AS name, pr.status AS status, pr.target_date AS target_date, pr.summary AS summary,
       lead.name AS lead, count(DISTINCT m) AS members, collect(DISTINCT x.id) AS scope
ORDER BY id
"""

PROJECT = """
MATCH (pr:Project {id:$id})
OPTIONAL MATCH (lead:Person)-[:LEADS]->(pr)
RETURN pr.id AS id, pr.name AS name, pr.status AS status, pr.start_date AS start_date,
       pr.target_date AS target_date, pr.summary AS summary, lead.name AS lead, lead.id AS lead_id
"""

PROJECT_MEMBERS = """
MATCH (m:Person)-[w:WORKS_ON]->(:Project {id:$id})
OPTIONAL MATCH (m)-[:MEMBER_OF]->(t:Team)
RETURN m.id AS id, m.name AS name, w.role AS role, t.name AS team ORDER BY name
"""

PROJECT_SCOPE = """
MATCH (:Project {id:$id})-[:COVERS]->(x)
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.status, x.id) AS name ORDER BY label, id
"""

# Decisions that touch anything in the project's scope, including its alternates.
PROJECT_DECISIONS = """
MATCH (:Project {id:$id})-[:COVERS]->(x)
MATCH (d:Decision)-[:ABOUT]->(s:Item)
WHERE s = x OR (s)-[:ALTERNATE_OF]-(x)
OPTIONAL MATCH (d)-[:DECIDED_BY]->(who:Person)
RETURN DISTINCT d.id AS id, d.outcome AS outcome, s.id AS subject, d.summary AS summary,
       d.decided_at AS decided_at, who.name AS decided_by
"""

# Open tasks that touch the project's scope, directly or through the builds and orders it covers.
PROJECT_TASKS = """
MATCH (:Project {id:$id})-[:COVERS]->(x)
MATCH (a:Action)-[:CONCERNS]->(x)
OPTIONAL MATCH (a)-[:ASSIGNED_TO]->(p:Person)
RETURN DISTINCT a.id AS id, a.title AS title, a.status AS status, p.name AS owner, x.id AS via
"""

PROJECT_ACTIVITY = """
MATCH (pr:Project {id:$id})
MATCH (c:Chunk)-[:MENTIONS]->(x) WHERE (x = pr OR (pr)-[:COVERS]->(x)) AND c.retracted_at IS NULL
MATCH (c)-[:PART_OF]->(s:Source)
RETURN DISTINCT c.id AS chunk, c.text AS text, c.author AS author, c.ts AS ts, s.title AS title
ORDER BY ts DESC LIMIT 8
"""

# Recent activity across the company, newest first.
CHANGES = """
MATCH (c:Chunk)-[:PART_OF]->(s:Source)
WHERE c.ts IS NOT NULL AND c.retracted_at IS NULL AND NOT c.id ENDS WITH '#title'
  AND (s.kind IN ['chat', 'ticket'] OR c.ordinal = 1)
RETURN CASE s.kind WHEN 'notice' THEN 'notice' WHEN 'doc' THEN 'document' ELSE 'message' END AS kind, c.ts AS at, c.author AS who, s.title AS what, c.text AS detail, c.id AS ref
UNION ALL
MATCH (d:Decision) OPTIONAL MATCH (d)-[:DECIDED_BY]->(p:Person)
RETURN 'decision' AS kind, d.decided_at AS at, p.name AS who, d.id + ' · ' + d.outcome AS what,
       d.summary AS detail, d.id AS ref
UNION ALL
MATCH (inv:Investigation)-[:CONCERNS]->(i:Item)
RETURN 'investigation' AS kind, inv.created_at AS at, inv.approved_by AS who, 'Impact of ' + i.id + ' approved' AS what,
       'Cost increase ' + coalesce(inv.cost_total, 'unknown') AS detail, inv.id AS ref
UNION ALL
MATCH (s:Supplier)-[:QUOTED]->(q:Quote)-[:FOR]->(i:Item)
RETURN 'quote' AS kind, q.valid_from AS at, s.name AS who, q.id + ' for ' + i.id AS what,
       q.currency + ' ' + q.unit_price + ', valid to ' + q.valid_until AS detail, q.id AS ref
"""

# Knowledge that may no longer be true, found by structure rather than by reading.
STALE_EVIDENCE = """
MATCH (n)-[e:EVIDENCED_BY|CITES]->(c:Chunk)
WHERE c.retracted_at IS NOT NULL OR (e.text_hash IS NOT NULL AND e.text_hash <> c.text_hash)
RETURN n.id AS record, labels(n)[0] AS label, c.id AS chunk,
       CASE WHEN c.retracted_at IS NOT NULL THEN 'source passage was removed'
            ELSE 'source passage was edited after it was relied on' END AS reason
"""

STALE_DECISIONS = """
MATCH (d:Decision)-[:APPLIES_TO]->(r:Revision) WHERE r.status <> 'released'
RETURN d.id AS record, 'Decision' AS label, r.id AS chunk,
       'applies to ' + r.id + ', which is now ' + r.status AS reason
"""

EXPIRING_QUOTES = """
MATCH (s:Supplier)-[:QUOTED]->(q:Quote)-[:FOR]->(i:Item)
WHERE q.valid_until >= $today AND q.valid_until <= $soon
RETURN q.id AS record, 'Quote' AS label, i.id AS chunk,
       s.name + ' quote for ' + i.id + ' expires ' + q.valid_until AS reason
"""

UNOWNED = """
MATCH (b:Build)-[:BUILDS]->(:Revision) WHERE NOT (:Person)-[:OWNS]->(b)
RETURN b.id AS record, 'Build' AS label, NULL AS chunk, 'no planner recorded' AS reason
UNION ALL
MATCH (c:Customer) WHERE NOT (:Person)-[:OWNS]->(c)
RETURN c.id AS record, 'Customer' AS label, NULL AS chunk, 'no account manager recorded' AS reason
"""


def resolve(graph: Graph, text: str, trace: Trace | None = None) -> list[dict]:
    t = trace or Trace(graph)
    return t.run("resolve_any", RESOLVE_ANY, {"text": text.strip()})


def who_knows(graph: Graph, text: str) -> dict:
    t = Trace(graph)
    found = resolve(graph, text, t)
    if len(found) != 1:
        hits = t.run("search_passages", """
            CALL db.idx.fulltext.queryNodes('Chunk', $q) YIELD node, score
            WITH node WHERE node.author IS NOT NULL AND node.retracted_at IS NULL
            RETURN node.author AS name, count(node) AS passages, collect(node.id)[0..3] AS evidence
            ORDER BY passages DESC LIMIT 5""", {"q": text})
        return {"subject": None, "candidates": found, "by_text": hits, "people": [], "trace": t.steps}
    subject = found[0]
    signals = t.run("who_knows", WHO_KNOWS, {"id": subject["id"]})
    people: dict[str, dict] = {}
    for s in signals:
        p = people.setdefault(s["person"], {"id": s["person"], "score": 0, "signals": []})
        p["score"] += s["weight"]
        p["signals"].append({"signal": s["signal"], "evidence": s["evidence"], "ts": s["ts"]})
    names = {r["id"]: r for r in t.run("people_names", """
        MATCH (p:Person) WHERE p.id IN $ids OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
        RETURN p.id AS id, p.name AS name, p.role AS role, t.name AS team""", {"ids": list(people)})}
    ranked = sorted(people.values(), key=lambda p: -p["score"])
    for p in ranked:
        p |= names.get(p["id"], {})
    return {"subject": subject, "people": ranked, "trace": t.steps}


def person(graph: Graph, person_id: str) -> dict | None:
    t = Trace(graph)
    found = t.run("person", PERSON, {"id": person_id})
    if not found:
        return None
    return found[0] | {
        "owns": t.run("person_owns", PERSON_OWNS, {"id": person_id}),
        "projects": t.run("person_projects", PERSON_PROJECTS, {"id": person_id}),
        "decisions": t.run("person_decisions", PERSON_DECISIONS, {"id": person_id}),
        "tasks": t.run("person_tasks", PERSON_TASKS, {"id": person_id}),
        "topics": t.run("person_topics", PERSON_TOPICS, {"id": person_id}),
        "recent": t.run("person_recent", PERSON_RECENT, {"id": person_id}),
        "trace": t.steps,
    }


def project(graph: Graph, project_id: str) -> dict | None:
    t = Trace(graph)
    found = t.run("project", PROJECT, {"id": project_id})
    if not found:
        return None
    return found[0] | {
        "members": t.run("project_members", PROJECT_MEMBERS, {"id": project_id}),
        "scope": t.run("project_scope", PROJECT_SCOPE, {"id": project_id}),
        "decisions": t.run("project_decisions", PROJECT_DECISIONS, {"id": project_id}),
        "tasks": t.run("project_tasks", PROJECT_TASKS, {"id": project_id}),
        "activity": t.run("project_activity", PROJECT_ACTIVITY, {"id": project_id}),
        "trace": t.steps,
    }


def changes(graph: Graph, today: date | None = None, limit: int = 40) -> dict:
    t = Trace(graph)
    today = today or date.today()
    feed = [r for r in t.run("changes", CHANGES, {}) if r["at"]]
    feed.sort(key=lambda r: r["at"], reverse=True)
    attention = (t.run("stale_evidence", STALE_EVIDENCE, {})
                 + t.run("stale_decisions", STALE_DECISIONS, {})
                 + t.run("expiring_quotes", EXPIRING_QUOTES,
                         {"today": today.isoformat(), "soon": (today + timedelta(days=90)).isoformat()})
                 + t.run("unowned", UNOWNED, {}))
    return {"feed": feed[:limit], "attention": attention, "trace": t.steps}
