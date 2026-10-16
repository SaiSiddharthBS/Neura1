"""Graph explorer and record timelines.

`neighborhood` returns the records directly connected to one record (passages are summarised as their sources),
for an interactive, expandable view. `timeline` returns everything that happened to a record, in date order,
gathered from decisions, quotes, messages, tasks, status changes, investigations, builds, orders and leave.
"""

from falkordb import Graph

from neura1.graph import rows

HIDDEN = ["Chunk", "Message", "Turn", "Event", "Alias", "Channel", "Conversation"]

NEIGHBORHOOD = """
MATCH (x {id:$id})-[r]-(n)
WHERE NOT any(l IN labels(n) WHERE l IN $hidden)
RETURN x.id AS center, labels(x)[0] AS center_label, coalesce(x.name, x.title, x.id) AS center_name,
       n.id AS id, labels(n)[0] AS label, coalesce(n.name, n.title, n.id) AS name,
       type(r) AS rel, startNode(r) = x AS outgoing
LIMIT $limit
"""

# Documents that talk about the record, through their passages.
SOURCES = """
MATCH (x {id:$id})<-[:MENTIONS]-(c:Chunk)-[:PART_OF]->(s:Source)
RETURN s.id AS id, s.kind AS kind, s.title AS name, count(c) AS passages
ORDER BY passages DESC LIMIT 8
"""

TIMELINE = """
MATCH (x {id:$id}) WHERE NOT x:Absence AND NOT x:Person
WITH x, coalesce(x.decided_at, x.created_at, x.valid_from, x.ts) AS at WHERE at IS NOT NULL
RETURN at, toLower(labels(x)[0]) AS kind, coalesce(x.title, x.summary, x.name, x.id) AS title,
       coalesce(x.reason, x.status, '') AS detail, x.id AS ref
UNION ALL
MATCH (x {id:$id})-[:EVIDENCED_BY]->(c:Chunk)-[:PART_OF]->(s:Source) WHERE c.ts IS NOT NULL
RETURN c.ts AS at, s.kind AS kind, s.title + coalesce(' · ' + c.author, '') AS title, c.text AS detail, c.id AS ref
UNION ALL
MATCH (x {id:$id})<-[:ABOUT]-(d:Decision)
RETURN d.decided_at AS at, 'decision' AS kind, d.id + ' · ' + d.outcome AS title, d.summary AS detail, d.id AS ref
UNION ALL
MATCH (x {id:$id})<-[:FOR]-(q:Quote)<-[:QUOTED]-(s:Supplier)
RETURN q.valid_from AS at, 'quote' AS kind, q.id + ' from ' + s.name AS title,
       q.currency + ' ' + q.unit_price + ', ' + toString(q.lead_weeks) + ' wk lead, valid to ' + q.valid_until AS detail, q.id AS ref
UNION ALL
MATCH (x {id:$id})<-[:MENTIONS]-(c:Chunk)-[:PART_OF]->(s:Source)
WHERE c.ts IS NOT NULL AND NOT c.text STARTS WITH '#' AND c.retracted_at IS NULL
RETURN c.ts AS at, s.kind AS kind, s.title + coalesce(' · ' + c.author, '') AS title, c.text AS detail, c.id AS ref
UNION ALL
MATCH (x {id:$id})<-[:CONCERNS]-(a:Action)
OPTIONAL MATCH (a)-[:ASSIGNED_TO]->(p:Person)
RETURN a.created_at AS at, 'task' AS kind, a.title AS title,
       coalesce(p.name, 'unassigned') + ' · ' + coalesce(a.status, 'open') AS detail, a.id AS ref
UNION ALL
MATCH (x {id:$id})<-[:CONCERNS]-(a:Action)<-[:ON]-(e:Event)
RETURN e.at AS at, 'status' AS kind, a.title AS title, e.by + ' moved it from ' + e.from + ' to ' + e.to AS detail, a.id AS ref
UNION ALL
MATCH (x {id:$id})<-[:CONCERNS]-(inv:Investigation)
RETURN inv.created_at AS at, 'plan' AS kind, 'Plan approved (' + coalesce(inv.kind, 'supplier_change') + ')' AS title,
       'by ' + coalesce(inv.approved_by, '') AS detail, inv.id AS ref
UNION ALL
MATCH (x {id:$id})-[:HAS_ABSENCE]->(a:Absence)
RETURN a.start_date AS at, 'leave' AS kind, 'Leave until ' + a.end_date AS title, coalesce(a.kind, '') AS detail, a.id AS ref
UNION ALL
MATCH (x {id:$id})<-[:ASSIGNED_TO]-(a:Action) WHERE a.completed_at IS NOT NULL
RETURN a.completed_at AS at, 'finished' AS kind, a.title AS title, 'finished' AS detail, a.id AS ref
"""


def neighborhood(graph: Graph, record_id: str, limit: int = 60) -> dict:
    found = rows(graph, NEIGHBORHOOD, {"id": record_id, "hidden": HIDDEN, "limit": limit})
    center = rows(graph, "MATCH (x {id:$id}) RETURN x.id AS id, labels(x)[0] AS label, "
                         "coalesce(x.name, x.title, x.id) AS name LIMIT 1", {"id": record_id})
    if not center:
        return {"nodes": [], "edges": []}
    nodes = {center[0]["id"]: center[0]}
    edges = []
    for r in found:
        nodes.setdefault(r["id"], {"id": r["id"], "label": r["label"], "name": r["name"]})
        a, b = (record_id, r["id"]) if r["outgoing"] else (r["id"], record_id)
        edges.append({"source": a, "target": b, "label": r["rel"]})
    for s in rows(graph, SOURCES, {"id": record_id}):
        nodes.setdefault(s["id"], {"id": s["id"], "label": "Source", "name": s["name"], "kind": s["kind"]})
        edges.append({"source": s["id"], "target": record_id, "label": f"mentions ×{s['passages']}"})
    return {"center": record_id, "nodes": list(nodes.values()), "edges": edges}


def timeline(graph: Graph, record_id: str) -> list[dict]:
    events = [e for e in rows(graph, TIMELINE, {"id": record_id}) if e["at"]]
    seen, out = set(), []
    for e in sorted(events, key=lambda e: e["at"], reverse=True):
        key = (e["kind"], e["ref"], e["at"][:10])
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out
