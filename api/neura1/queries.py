"""Named, parameterised Cypher. This module is the catalogue the product depends on."""

# Where-used with quantity roll-up.
# Walks CONTAINS edges from every product revision down to the part. Every revision on the
# path (the top-level product revision and any sub-assembly revision) must be released.
# Quantity per unit is the product of qty along a path; separate paths (repeated
# occurrences) are summed, never de-duplicated.
WHERE_USED = """
MATCH (prod:Item {kind:'product'})-[:HAS_REV]->(top:Revision)
MATCH p = (top)-[:CONTAINS*1..8]->(part:Item {id:$item_id})
WITH prod, top, p,
     [n IN nodes(p) WHERE n:Revision AND n.status <> 'released' | n.id] AS blocked,
     reduce(q = 1, r IN relationships(p) | q * r.qty) AS path_qty
WITH prod, top,
     sum(CASE WHEN size(blocked) = 0 THEN path_qty ELSE 0 END) AS qty_per_unit,
     sum(path_qty) AS qty_if_built,
     collect({nodes: [n IN nodes(p) | n.id], qty: path_qty,
              refdes: [r IN relationships(p) | r.refdes], blocked_by: blocked}) AS paths
RETURN prod.id AS product, top.id AS revision, top.status AS status,
       qty_per_unit > 0 AS applicable, toInteger(qty_per_unit) AS qty_per_unit,
       toInteger(qty_if_built) AS qty_if_built, paths
ORDER BY revision
"""

# Resolve a part number or id as written in a notice to exactly one item. Zero or several matches
# means the system stops and asks, rather than guessing.
RESOLVE_ITEM = """
MATCH (i:Item) WHERE toUpper(i.id) = toUpper($text) OR toUpper(i.mpn) = toUpper($text)
RETURN i.id AS id, i.kind AS kind, i.name AS name, i.mpn AS mpn, i.manufacturer AS manufacturer,
       i.on_hand AS on_hand, i.allocated AS allocated
"""

# Near matches when a notice names a part we cannot resolve exactly (shown to the user, never auto-picked).
SUGGEST_ITEMS = """
MATCH (i:Item)
WHERE toUpper(i.id) CONTAINS toUpper($text)
   OR (i.mpn <> '' AND (toUpper(i.mpn) CONTAINS toUpper($text) OR toUpper($text) CONTAINS toUpper(i.mpn)))
   OR toLower(i.name) CONTAINS toLower($text)
RETURN i.id AS id, i.kind AS kind, i.name AS name, i.mpn AS mpn LIMIT 8
"""

# Builds of the applicable revisions, the orders they fulfil, the customers, and who owns each.
EXPOSURE = """
MATCH (b:Build)-[:BUILDS]->(r:Revision) WHERE r.id IN $revisions
OPTIONAL MATCH (planner:Person)-[:OWNS]->(b)
OPTIONAL MATCH (c:Customer)-[:PLACED]->(o:Order)-[:FULFILLED_BY]->(b)
OPTIONAL MATCH (am:Person)-[:OWNS]->(c)
RETURN b.id AS build, r.id AS revision, b.qty AS build_qty, b.planned_date AS planned_date,
       planner.name AS planner,
       collect(CASE WHEN o IS NULL THEN NULL ELSE
         {order: o.id, qty: o.qty, due: o.due_date, penalty: o.penalty_note,
          customer: c.name, customer_id: c.id, account_manager: am.name} END) AS orders
ORDER BY planned_date
"""

# Units already in the field on any revision that contains the part (obsolete ones included).
FIELD_UNITS = """
MATCH (s:Shipment)-[:OF_REV]->(r:Revision)-[:CONTAINS*1..8]->(:Item {id:$item_id})
MATCH (s)-[:SHIPPED_TO]->(c:Customer)
RETURN DISTINCT s.id AS shipment, r.id AS revision, r.status AS status, s.qty AS qty,
       s.shipped_on AS shipped_on, c.name AS customer
"""

# Firmware, tests, and anything else recorded as depending on the part, with owners.
DEPENDENTS = """
MATCH (d:Item)-[dep:DEPENDS_ON]->(:Item {id:$item_id})
OPTIONAL MATCH (owner:Person)-[:OWNS]->(d)
OPTIONAL MATCH (owner)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (ch:Chunk)-[:MENTIONS]->(d)
OPTIONAL MATCH (ch)-[:PART_OF]->(src:Source)
RETURN d.id AS id, d.kind AS kind, d.name AS name, dep.note AS note, owner.name AS owner, t.name AS team,
       collect(DISTINCT {chunk: ch.id, source: src.id, title: src.title}) AS evidence
"""

# Assemblies whose revisions directly contain the part, and their owners.
DIRECT_PARENTS = """
MATCH (pi:Item)-[:HAS_REV]->(pr:Revision)-[c:CONTAINS]->(:Item {id:$item_id})
WHERE pr.id IN $revisions
OPTIONAL MATCH (owner:Person)-[:OWNS]->(pi)
RETURN DISTINCT pi.id AS item, pi.name AS name, collect(DISTINCT pr.id) AS revisions,
       owner.name AS owner
"""

QUOTES = """
MATCH (s:Supplier)-[:QUOTED]->(q:Quote)-[:FOR]->(:Item {id:$item_id})
RETURN q.id AS id, s.name AS supplier, q.unit_price AS unit_price, q.currency AS currency, q.moq AS moq,
       q.lead_weeks AS lead_weeks, q.valid_from AS valid_from, q.valid_until AS valid_until,
       q.authority AS authority, q.source AS source
"""

# Alternates of the part. `basis` says why it is listed (a cross-reference is not an approval).
ALTERNATES = """
MATCH (alt:Item)-[a:ALTERNATE_OF]-(:Item {id:$item_id})
RETURN alt.id AS id, alt.name AS name, alt.manufacturer AS manufacturer, a.basis AS basis, a.note AS note
"""

# Recorded decisions about the part or any of its alternates, with who decided and verbatim evidence.
DECISIONS = """
MATCH (part:Item {id:$item_id})
MATCH (d:Decision)-[:ABOUT]->(subject:Item)
WHERE subject = part OR (subject)-[:ALTERNATE_OF]-(part)
OPTIONAL MATCH (d)-[:DECIDED_BY]->(who:Person)
OPTIONAL MATCH (d)-[:APPLIES_TO]->(r:Revision)
OPTIONAL MATCH (d)-[e:EVIDENCED_BY]->(ch:Chunk)-[:PART_OF]->(src:Source)
RETURN d.id AS id, subject.id AS subject, d.outcome AS outcome, d.summary AS summary, d.reason AS reason,
       d.decided_at AS decided_at, d.authority AS authority, d.status AS status, who.name AS decided_by,
       d.extracted_by AS extracted_by, collect(DISTINCT r.id) AS applies_to,
       collect(DISTINCT {chunk: ch.id, source: src.id, title: src.title, quote: e.quote, page: ch.page,
                         author: ch.author, ts: ch.ts, rank: e.rank}) AS evidence
ORDER BY decided_at
"""

# Passages that mention any of the given entities (used to show supporting context).
EVIDENCE_FOR = """
MATCH (ch:Chunk)-[:MENTIONS]->(x) WHERE x.id IN $ids
MATCH (ch)-[:PART_OF]->(src:Source)
RETURN ch.id AS chunk, src.id AS source, src.title AS title, src.kind AS kind, ch.text AS text,
       ch.author AS author, ch.ts AS ts, ch.page AS page, collect(x.id) AS mentions
ORDER BY ch.ts
"""

# The passage of a policy document that holds its numbered clauses, so tasks can cite it.
POLICY_CHUNK = """
MATCH (ch:Chunk)-[:PART_OF]->(s:Source {ref:$ref})
WHERE ch.text CONTAINS '1. '
RETURN ch.id AS chunk, s.id AS source, s.title AS title LIMIT 1
"""

# Full-text search over every passage (FalkorDB full-text index on Chunk.text).
SEARCH_PASSAGES = """
CALL db.idx.fulltext.queryNodes('Chunk', $q) YIELD node, score
MATCH (node)-[:PART_OF]->(src:Source)
RETURN node.id AS chunk, src.title AS title, src.kind AS kind, node.text AS text, node.author AS author,
       node.page AS page, score
ORDER BY score DESC LIMIT $limit
"""
