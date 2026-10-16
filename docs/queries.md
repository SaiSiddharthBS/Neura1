# Cypher queries Neura1 depends on

Generated from [`api/neura1/queries.py`](../api/neura1/queries.py) (change impact) and [`api/neura1/brain.py`](../api/neura1/brain.py) (company-wide questions) by `uv run python -m neura1.docs`.
All queries are parameterised and run read-only (`GRAPH.RO_QUERY`). Writes happen only in the loaders
(`api/neura1/ingest/`) and in `api/neura1/actions.py`.

# Change impact

## `WHERE_USED`

Where-used with quantity roll-up. Walks CONTAINS edges from every product revision down to the part. Every revision on the path (the top-level product revision and any sub-assembly revision) must be released. Quantity per unit is the product of qty along a path; separate paths (repeated occurrences) are summed, never de-duplicated.

**Parameters:** `$item_id`  
**Used by:** Impact workspace (graph, Engineering tab), cost scenario

```cypher
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
```

## `RESOLVE_ITEM`

Resolve a part number or id as written in a notice to exactly one item. Zero or several matches means the system stops and asks, rather than guessing.

**Parameters:** `$text`  
**Used by:** Every analysis: notice part number → internal item

```cypher
MATCH (i:Item) WHERE toUpper(i.id) = toUpper($text) OR toUpper(i.mpn) = toUpper($text)
RETURN i.id AS id, i.kind AS kind, i.name AS name, i.mpn AS mpn, i.manufacturer AS manufacturer,
       i.on_hand AS on_hand, i.allocated AS allocated
```

## `SUGGEST_ITEMS`

Near matches when a notice names a part we cannot resolve exactly (shown to the user, never auto-picked).

**Parameters:** `$text`  
**Used by:** Unresolved part numbers in notices (suggestions, never auto-picked)

```cypher
MATCH (i:Item)
WHERE toUpper(i.id) CONTAINS toUpper($text)
   OR (i.mpn <> '' AND (toUpper(i.mpn) CONTAINS toUpper($text) OR toUpper($text) CONTAINS toUpper(i.mpn)))
   OR toLower(i.name) CONTAINS toLower($text)
RETURN i.id AS id, i.kind AS kind, i.name AS name, i.mpn AS mpn LIMIT 8
```

## `EXPOSURE`

Builds of the applicable revisions, the orders they fulfil, the customers, and who owns each.

**Parameters:** `$revisions`  
**Used by:** Production and Sales tabs, builds-at-risk, customer tasks

```cypher
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
```

## `FIELD_UNITS`

Units already in the field on any revision that contains the part (obsolete ones included).

**Parameters:** `$item_id`  
**Used by:** Support tab

```cypher
MATCH (s:Shipment)-[:OF_REV]->(r:Revision)-[:CONTAINS*1..8]->(:Item {id:$item_id})
MATCH (s)-[:SHIPPED_TO]->(c:Customer)
RETURN DISTINCT s.id AS shipment, r.id AS revision, r.status AS status, s.qty AS qty,
       s.shipped_on AS shipped_on, c.name AS customer
```

## `DEPENDENTS`

Firmware, tests, and anything else recorded as depending on the part, with owners.

**Parameters:** `$item_id`  
**Used by:** Engineering tab, firmware and requalification tasks

```cypher
MATCH (d:Item)-[dep:DEPENDS_ON]->(:Item {id:$item_id})
OPTIONAL MATCH (owner:Person)-[:OWNS]->(d)
OPTIONAL MATCH (owner)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (ch:Chunk)-[:MENTIONS]->(d)
OPTIONAL MATCH (ch)-[:PART_OF]->(src:Source)
RETURN d.id AS id, d.kind AS kind, d.name AS name, dep.note AS note, owner.name AS owner, t.name AS team,
       collect(DISTINCT {chunk: ch.id, source: src.id, title: src.title}) AS evidence
```

## `DIRECT_PARENTS`

Assemblies whose revisions directly contain the part, and their owners.

**Parameters:** `$item_id`, `$revisions`  
**Used by:** Engineering change review tasks

```cypher
MATCH (pi:Item)-[:HAS_REV]->(pr:Revision)-[c:CONTAINS]->(:Item {id:$item_id})
WHERE pr.id IN $revisions
OPTIONAL MATCH (owner:Person)-[:OWNS]->(pi)
RETURN DISTINCT pi.id AS item, pi.name AS name, collect(DISTINCT pr.id) AS revisions,
       owner.name AS owner
```

## `QUOTES`



**Parameters:** `$item_id`  
**Used by:** Procurement tab, cost baseline

```cypher
MATCH (s:Supplier)-[:QUOTED]->(q:Quote)-[:FOR]->(:Item {id:$item_id})
RETURN q.id AS id, s.name AS supplier, q.unit_price AS unit_price, q.currency AS currency, q.moq AS moq,
       q.lead_weeks AS lead_weeks, q.valid_from AS valid_from, q.valid_until AS valid_until,
       q.authority AS authority, q.source AS source
```

## `ALTERNATES`

Alternates of the part. `basis` says why it is listed (a cross-reference is not an approval).

**Parameters:** `$item_id`  
**Used by:** Alternate banners

```cypher
MATCH (alt:Item)-[a:ALTERNATE_OF]-(:Item {id:$item_id})
RETURN alt.id AS id, alt.name AS name, alt.manufacturer AS manufacturer, a.basis AS basis, a.note AS note
```

## `DECISIONS`

Recorded decisions about the part or any of its alternates, with who decided and verbatim evidence.

**Parameters:** `$item_id`  
**Used by:** Rejected/pending alternate banners, decision nodes in the graph

```cypher
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
```

## `EVIDENCE_FOR`

Passages that mention any of the given entities (used to show supporting context).

**Parameters:** `$ids`  
**Used by:** Evidence lookups

```cypher
MATCH (ch:Chunk)-[:MENTIONS]->(x) WHERE x.id IN $ids
MATCH (ch)-[:PART_OF]->(src:Source)
RETURN ch.id AS chunk, src.id AS source, src.title AS title, src.kind AS kind, ch.text AS text,
       ch.author AS author, ch.ts AS ts, ch.page AS page, collect(x.id) AS mentions
ORDER BY ch.ts
```

## `POLICY_CHUNK`

The passage of a policy document that holds its numbered clauses, so tasks can cite it.

**Parameters:** `$ref`  
**Used by:** Task citations

```cypher
MATCH (ch:Chunk)-[:PART_OF]->(s:Source {ref:$ref})
WHERE ch.text CONTAINS '1. '
RETURN ch.id AS chunk, s.id AS source, s.title AS title LIMIT 1
```

## `SEARCH_PASSAGES`

Full-text search over every passage (FalkorDB full-text index on Chunk.text).

**Parameters:** `$limit`, `$q`  
**Used by:** Company brain search

```cypher
CALL db.idx.fulltext.queryNodes('Chunk', $q) YIELD node, score
MATCH (node)-[:PART_OF]->(src:Source)
RETURN node.id AS chunk, src.title AS title, src.kind AS kind, node.text AS text, node.author AS author,
       node.page AS page, score
ORDER BY score DESC LIMIT $limit
```

# The wider company brain

## `RESOLVE_ANY`

Anything a person might ask about, found by id, name, or an alias used in chats.

**Parameters:** `$text`  
**Used by:** Who knows · Ask agent · MCP: name, id or chat alias → record

```cypher
MATCH (x)
WHERE (x:Item OR x:Revision OR x:Project OR x:Customer OR x:Order OR x:Build OR x:Person OR x:Team OR x:Supplier)
  AND (toUpper(x.id) = toUpper($text) OR toLower(x.name) = toLower($text) OR toUpper(x.mpn) = toUpper($text))
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.id) AS name
UNION
MATCH (a:Alias)-[:REFERS_TO]->(x) WHERE toLower(a.term) = toLower($text)
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.id) AS name
```

## `WHO_KNOWS`

Who knows about a record, and why. Each branch is one kind of signal with a weight; the evidence column names the record or passage that supports it.

**Parameters:** `$id`  
**Used by:** Who knows about… (Company brain), Ask and MCP `who_knows`

```cypher
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
```

## `PERSON`



**Parameters:** `$id`  
**Used by:** People page

```cypher
MATCH (p:Person {id:$id})
OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p)
OPTIONAL MATCH (p)-[:BACKS_UP]->(covers:Person)
RETURN p.id AS id, p.name AS name, p.role AS role, t.name AS team,
       collect(DISTINCT b.name) AS backed_up_by, collect(DISTINCT covers.name) AS backs_up
```

## `PERSON_OWNS`



**Parameters:** `$id`  
**Used by:** People page

```cypher
MATCH (:Person {id:$id})-[:OWNS]->(x)
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.id) AS name ORDER BY label, id
```

## `PERSON_PROJECTS`



**Parameters:** `$id`  
**Used by:** People page

```cypher
MATCH (p:Person {id:$id})-[r:WORKS_ON|LEADS]->(pr:Project)
RETURN pr.id AS id, pr.name AS name, pr.status AS status, collect(DISTINCT coalesce(r.role, 'lead')) AS roles
ORDER BY id
```

## `PERSON_DECISIONS`



**Parameters:** `$id`  
**Used by:** People page

```cypher
MATCH (:Person {id:$id})<-[:DECIDED_BY]-(d:Decision)-[:ABOUT]->(s:Item)
RETURN d.id AS id, d.outcome AS outcome, s.id AS subject, d.summary AS summary, d.decided_at AS decided_at
ORDER BY decided_at DESC
```

## `PERSON_TASKS`



**Parameters:** `$id`  
**Used by:** People page

```cypher
MATCH (:Person {id:$id})<-[:ASSIGNED_TO]-(a:Action)
OPTIONAL MATCH (inv:Investigation)-[:PRODUCED]->(a)
RETURN a.id AS id, a.title AS title, a.status AS status, a.created_at AS created_at, inv.id AS investigation
ORDER BY created_at DESC
```

## `PERSON_TOPICS`

What a person talks about, from passages attributed to them: their working knowledge.

**Parameters:** `$id`  
**Used by:** People page · what they know

```cypher
MATCH (:Person {id:$id})<-[:SAID_BY]-(c:Chunk)-[:MENTIONS]->(x)
WHERE NOT x:Person AND NOT x:Source AND c.retracted_at IS NULL
RETURN x.id AS id, labels(x)[0] AS label, count(c) AS mentions, max(c.ts) AS last
ORDER BY mentions DESC LIMIT 12
```

## `PERSON_RECENT`



**Parameters:** `$id`  
**Used by:** People page

```cypher
MATCH (:Person {id:$id})<-[:SAID_BY]-(c:Chunk)-[:PART_OF]->(s:Source)
WHERE c.retracted_at IS NULL
RETURN c.id AS chunk, c.text AS text, c.ts AS ts, s.title AS title ORDER BY ts DESC LIMIT 6
```

## `PEOPLE`



**Parameters:** none  
**Used by:** People directory

```cypher
MATCH (p:Person)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (p)-[:OWNS]->(x)
OPTIONAL MATCH (p)-[:WORKS_ON|LEADS]->(pr:Project)
RETURN p.id AS id, p.name AS name, p.role AS role, t.name AS team,
       count(DISTINCT x) AS owns, collect(DISTINCT pr.id) AS projects
ORDER BY team, name
```

## `PROJECTS`



**Parameters:** none  
**Used by:** Projects page

```cypher
MATCH (pr:Project)
OPTIONAL MATCH (lead:Person)-[:LEADS]->(pr)
OPTIONAL MATCH (m:Person)-[:WORKS_ON]->(pr)
OPTIONAL MATCH (pr)-[:COVERS]->(x)
RETURN pr.id AS id, pr.name AS name, pr.status AS status, pr.target_date AS target_date, pr.summary AS summary,
       lead.name AS lead, count(DISTINCT m) AS members, collect(DISTINCT x.id) AS scope
ORDER BY id
```

## `PROJECT`



**Parameters:** `$id`  
**Used by:** Project detail

```cypher
MATCH (pr:Project {id:$id})
OPTIONAL MATCH (lead:Person)-[:LEADS]->(pr)
RETURN pr.id AS id, pr.name AS name, pr.status AS status, pr.start_date AS start_date,
       pr.target_date AS target_date, pr.summary AS summary, lead.name AS lead, lead.id AS lead_id
```

## `PROJECT_MEMBERS`



**Parameters:** `$id`  
**Used by:** Project detail

```cypher
MATCH (m:Person)-[w:WORKS_ON]->(:Project {id:$id})
OPTIONAL MATCH (m)-[:MEMBER_OF]->(t:Team)
RETURN m.id AS id, m.name AS name, w.role AS role, t.name AS team ORDER BY name
```

## `PROJECT_SCOPE`



**Parameters:** `$id`  
**Used by:** Project detail

```cypher
MATCH (:Project {id:$id})-[:COVERS]->(x)
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.status, x.id) AS name ORDER BY label, id
```

## `PROJECT_DECISIONS`

Decisions that touch anything in the project's scope, including its alternates.

**Parameters:** `$id`  
**Used by:** Project detail

```cypher
MATCH (:Project {id:$id})-[:COVERS]->(x)
MATCH (d:Decision)-[:ABOUT]->(s:Item)
WHERE s = x OR (s)-[:ALTERNATE_OF]-(x)
OPTIONAL MATCH (d)-[:DECIDED_BY]->(who:Person)
RETURN DISTINCT d.id AS id, d.outcome AS outcome, s.id AS subject, d.summary AS summary,
       d.decided_at AS decided_at, who.name AS decided_by
```

## `PROJECT_TASKS`

Open tasks that touch the project's scope, directly or through the builds and orders it covers.

**Parameters:** `$id`  
**Used by:** Project detail

```cypher
MATCH (:Project {id:$id})-[:COVERS]->(x)
MATCH (a:Action)-[:CONCERNS]->(x)
OPTIONAL MATCH (a)-[:ASSIGNED_TO]->(p:Person)
RETURN DISTINCT a.id AS id, a.title AS title, a.status AS status, p.name AS owner, x.id AS via
```

## `PROJECT_ACTIVITY`



**Parameters:** `$id`  
**Used by:** Project detail

```cypher
MATCH (pr:Project {id:$id})
MATCH (c:Chunk)-[:MENTIONS]->(x) WHERE (x = pr OR (pr)-[:COVERS]->(x)) AND c.retracted_at IS NULL
MATCH (c)-[:PART_OF]->(s:Source)
RETURN DISTINCT c.id AS chunk, c.text AS text, c.author AS author, c.ts AS ts, s.title AS title
ORDER BY ts DESC LIMIT 8
```

## `CHANGES`

Recent activity across the company, newest first.

**Parameters:** none  
**Used by:** What's new feed

```cypher
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
```

## `STALE_EVIDENCE`

Knowledge that may no longer be true, found by structure rather than by reading.

**Parameters:** none  
**Used by:** What's new · needs attention

```cypher
MATCH (n)-[e:EVIDENCED_BY|CITES]->(c:Chunk)
WHERE c.retracted_at IS NOT NULL OR (e.text_hash IS NOT NULL AND e.text_hash <> c.text_hash)
RETURN n.id AS record, labels(n)[0] AS label, c.id AS chunk,
       CASE WHEN c.retracted_at IS NOT NULL THEN 'source passage was removed'
            ELSE 'source passage was edited after it was relied on' END AS reason
```

## `STALE_DECISIONS`



**Parameters:** none  
**Used by:** What's new · needs attention

```cypher
MATCH (d:Decision)-[:APPLIES_TO]->(r:Revision) WHERE r.status <> 'released'
RETURN d.id AS record, 'Decision' AS label, r.id AS chunk,
       'applies to ' + r.id + ', which is now ' + r.status AS reason
```

## `EXPIRING_QUOTES`



**Parameters:** `$soon`, `$today`  
**Used by:** What's new · needs attention

```cypher
MATCH (s:Supplier)-[:QUOTED]->(q:Quote)-[:FOR]->(i:Item)
WHERE q.valid_until >= $today AND q.valid_until <= $soon
RETURN q.id AS record, 'Quote' AS label, i.id AS chunk,
       s.name + ' quote for ' + i.id + ' expires ' + q.valid_until AS reason
```

## `UNOWNED`



**Parameters:** none  
**Used by:** What's new · needs attention

```cypher
MATCH (b:Build)-[:BUILDS]->(:Revision) WHERE NOT (:Person)-[:OWNS]->(b)
RETURN b.id AS record, 'Build' AS label, NULL AS chunk, 'no planner recorded' AS reason
UNION ALL
MATCH (c:Customer) WHERE NOT (:Person)-[:OWNS]->(c)
RETURN c.id AS record, 'Customer' AS label, NULL AS chunk, 'no account manager recorded' AS reason
```
