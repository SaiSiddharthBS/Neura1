# Cypher queries Neura1 depends on

Generated from [`queries.py`](../api/neura1/queries.py), [`brain.py`](../api/neura1/brain.py) and [`scenarios.py`](../api/neura1/scenarios.py), `people.py`, `search.py`, `memory.py` and `access.py` by `uv run python -m neura1.docs`.
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
WHERE (x:Item OR x:Revision OR x:Project OR x:Customer OR x:Order OR x:Build OR x:Person OR x:Team OR x:Supplier
       OR x:Skill OR x:Organization OR x:Certification)
  AND (toUpper(x.id) = toUpper($text) OR toLower(x.name) = toLower($text) OR toUpper(x.mpn) = toUpper($text))
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.id) AS name
UNION
MATCH (a:Alias)-[:REFERS_TO]->(x) WHERE toLower(a.term) = toLower($text)
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.id) AS name
```

## `LOOKUP`

Fast lookup for the command palette: anything whose id, name or part number contains the text.

**Parameters:** `$q`  
**Used by:** —

```cypher
MATCH (x)
WHERE (x:Item OR x:Project OR x:Person OR x:Customer OR x:Order OR x:Build OR x:Revision)
  AND (toLower(x.id) CONTAINS toLower($q) OR toLower(coalesce(x.name, '')) CONTAINS toLower($q)
       OR toLower(coalesce(x.mpn, '')) CONTAINS toLower($q))
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.id) AS name, x.kind AS kind
LIMIT 12
UNION
MATCH (x:Skill) WHERE toLower(x.name) CONTAINS toLower($q)
RETURN x.id AS id, 'Skill' AS label, x.name AS name, NULL AS kind
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
UNION ALL
MATCH (p:Person)-[:HAS_SKILL]->(x:Skill {id:$id})
RETURN p.id AS person, 'has the skill' AS signal, 4 AS weight, x.name AS evidence, NULL AS ts
UNION ALL
MATCH (p:Person)<-[:ASSIGNED_TO]-(a:Action)-[:CONCERNS]->(x {id:$id})
RETURN p.id AS person, CASE WHEN a.status = 'done' THEN 'finished work on it' ELSE 'working on it' END AS signal,
       CASE WHEN a.status = 'done' THEN 3 ELSE 2 END AS weight, a.id AS evidence, coalesce(a.completed_at, a.created_at) AS ts
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
MATCH (:Person {id:$id})<-[:ASSIGNED_TO]-(a:Action) WHERE coalesce(a.status, 'open') <> 'done'
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
WHERE c.retracted_at IS NULL AND NOT c.text STARTS WITH '#'
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
MATCH (a:Action)-[:CONCERNS]->(x) WHERE coalesce(a.status, 'open') <> 'done'
OPTIONAL MATCH (a)-[:ASSIGNED_TO]->(p:Person)
RETURN DISTINCT a.id AS id, a.title AS title, a.status AS status, p.name AS owner, x.id AS via
```

## `PROJECT_ACTIVITY`



**Parameters:** `$id`  
**Used by:** Project detail

```cypher
MATCH (pr:Project {id:$id})
MATCH (c:Chunk)-[:MENTIONS]->(x) WHERE (x = pr OR (pr)-[:COVERS]->(x)) AND c.retracted_at IS NULL AND NOT c.text STARTS WITH '#'
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
WHERE c.ts IS NOT NULL AND c.retracted_at IS NULL AND NOT c.id ENDS WITH '#title' AND NOT c.text STARTS WITH '#'
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
MATCH (e:Event {kind:'status_change'})-[:ON]->(a:Action)
RETURN 'task' AS kind, e.at AS at, e.by AS who, a.title AS what,
       'moved from ' + e.from + ' to ' + e.to AS detail, a.id AS ref
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

## `ACTION_ITEMS`



**Parameters:** none  
**Used by:** —

```cypher
MATCH (ai:ActionItem)-[:FOR]->(p:Person)
MATCH (ai)-[:FOUND_IN]->(c:Chunk)-[:PART_OF]->(s:Source)
RETURN ai.id AS id, ai.task AS task, ai.due AS due, ai.quote AS quote, ai.status AS status, p.name AS owner,
       c.id AS chunk, s.title AS meeting, c.ts AS at
ORDER BY at DESC
```

# Company events and the risk radar

## `PERSON_ABSENCES`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (p:Person {id:$id})-[:HAS_ABSENCE]->(a:Absence)
RETURN a.start_date AS start_date, a.end_date AS end_date, a.kind AS kind, a.note AS note ORDER BY start_date
```

## `PERSON_LINE`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (p:Person {id:$id})
OPTIONAL MATCH (p)-[:REPORTS_TO]->(m:Person)
OPTIONAL MATCH (r:Person)-[:REPORTS_TO]->(p)
OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p)
RETURN p.name AS name, p.role AS role, m.id AS manager_id, m.name AS manager,
       collect(DISTINCT r.name) AS reports, b.id AS backup_id, b.name AS backup
```

## `OWNED_WORK`

What the person owns, and what is scheduled or due on those things.

**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (p:Person {id:$id})-[:OWNS]->(x)
OPTIONAL MATCH (a:Action)-[:CONCERNS]->(x) WHERE coalesce(a.status, 'open') <> 'done'
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.id) AS name,
       x.planned_date AS planned_date, x.valid_until AS valid_until,
       collect(DISTINCT a.title) AS open_tasks_on_it
```

## `OPEN_TASKS`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (:Person {id:$id})<-[:ASSIGNED_TO]-(a:Action) WHERE coalesce(a.status, 'open') <> 'done'
OPTIONAL MATCH (inv:Investigation)-[:PRODUCED]->(a)
RETURN a.id AS id, a.title AS title, coalesce(a.status, 'open') AS status, inv.id AS investigation
```

## `LED_PROJECTS`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (:Person {id:$id})-[:LEADS]->(pr:Project) RETURN pr.id AS id, pr.name AS name, pr.target_date AS target_date
```

## `SOLE_KNOWLEDGE`

Things this person talks about that nobody else discusses or owns: knowledge that leaves with them.

**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (p:Person {id:$id})<-[:SAID_BY]-(c:Chunk)-[:MENTIONS]->(x)
WHERE NOT x:Person AND NOT x:Source AND c.retracted_at IS NULL
WITH p, x, count(c) AS mine
OPTIONAL MATCH (o:Person)<-[:SAID_BY]-(:Chunk)-[:MENTIONS]->(x) WHERE o <> p
WITH p, x, mine, count(DISTINCT o) AS others
OPTIONAL MATCH (o2:Person)-[:OWNS]->(x) WHERE o2 <> p
WITH x, mine, others, count(DISTINCT o2) AS other_owners
WHERE others = 0
RETURN x.id AS id, labels(x)[0] AS label, mine, other_owners
ORDER BY mine DESC
```

## `DECISIONS_MADE`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (:Person {id:$id})<-[:DECIDED_BY]-(d:Decision)-[:ABOUT]->(s:Item)
RETURN d.id AS id, d.outcome AS outcome, s.id AS subject, d.summary AS summary
```

## `HANDOVER_POLICY`



**Parameters:** none  
**Used by:** —

```cypher
MATCH (ch:Chunk)-[:PART_OF]->(:Source {ref:'HB-HR-02'}) WHERE ch.text CONTAINS '1. '
RETURN ch.id AS chunk LIMIT 1
```

## `CUSTOMER`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (c:Customer {id:$id})
OPTIONAL MATCH (am:Person)-[:OWNS]->(c)
OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(am)
RETURN c.id AS id, c.name AS name, am.id AS manager_id, am.name AS account_manager, b.name AS backup
```

## `CUSTOMER_ORDERS`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (c:Customer {id:$id})-[:PLACED]->(o:Order)
OPTIONAL MATCH (o)-[:FULFILLED_BY]->(b:Build)-[:BUILDS]->(r:Revision)
OPTIONAL MATCH (planner:Person)-[:OWNS]->(b)
OPTIONAL MATCH (a:Action)-[:CONCERNS]->(t) WHERE (t = o OR t = b) AND coalesce(a.status, 'open') <> 'done'
RETURN o.id AS id, o.qty AS qty, o.due_date AS due, o.unit_price AS unit_price,
       o.penalty_pct_per_week AS penalty_pct, o.penalty_cap_pct AS penalty_cap, o.penalty_note AS penalty_note,
       b.id AS build, b.planned_date AS build_date, r.id AS revision, planner.name AS planner,
       collect(DISTINCT a.title) AS open_tasks
ORDER BY due
```

## `CUSTOMER_FIELD`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (s:Shipment)-[:SHIPPED_TO]->(:Customer {id:$id})
MATCH (s)-[:OF_REV]->(r:Revision)
RETURN s.id AS id, s.qty AS qty, s.shipped_on AS shipped_on, r.id AS revision, r.status AS status
```

## `CUSTOMER_SIGNALS`

Tickets, escalations and conversations that mention the customer, its orders, or its field units.

**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (c:Customer {id:$id})
MATCH (ch:Chunk)-[:MENTIONS]->(x)
WHERE x = c OR (c)-[:PLACED]->(x)
MATCH (ch)-[:PART_OF]->(s:Source)
OPTIONAL MATCH (s)-[:ASSIGNED_TO]->(who:Person)
RETURN DISTINCT s.id AS source, s.kind AS kind, s.title AS title, s.status AS status, who.name AS assignee,
       max(ch.ts) AS last
ORDER BY last DESC
```

## `CUSTOMER_PROJECTS`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (pr:Project)-[:COVERS]->(x) WHERE x.id = $id OR (:Customer {id:$id})-[:PLACED]->(x)
OPTIONAL MATCH (lead:Person)-[:LEADS]->(pr)
RETURN DISTINCT pr.id AS id, pr.name AS name, pr.status AS status, lead.name AS lead
```

## `ORDER_BOOK`



**Parameters:** none  
**Used by:** —

```cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN c.id AS customer, sum(coalesce(o.unit_price, 0) * o.qty) AS value
```

## `FIX_PATH`

Products a ticket or escalation is about, and the projects and firmware leads that can fix them.

**Parameters:** `$source`  
**Used by:** —

```cypher
MATCH (s:Source {id:$source})<-[:PART_OF]-(:Chunk)-[:MENTIONS]->(prod:Item {kind:'product'})
MATCH (prod)-[:HAS_REV]->(r:Revision)<-[:COVERS]-(pr:Project)<-[:LEADS]-(lead:Person)
RETURN DISTINCT prod.id AS product, pr.id AS project, pr.name AS project_name, lead.name AS lead
```

## `TOP_OF_CHAIN`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (p:Person {id:$id})-[:REPORTS_TO*1..4]->(top:Person) WHERE NOT (top)-[:REPORTS_TO]->()
RETURN top.name AS name LIMIT 1
```

## `CUSTOMERS`



**Parameters:** none  
**Used by:** —

```cypher
MATCH (c:Customer)
OPTIONAL MATCH (am:Person)-[:OWNS]->(c)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.id AS id, c.name AS name, am.name AS account_manager, count(o) AS orders,
       sum(coalesce(o.unit_price, 0) * coalesce(o.qty, 0)) AS value
ORDER BY value DESC
```

## `CHOKEPOINTS`



**Parameters:** `$labels`, `$rels`  
**Used by:** —

```cypher
CALL algo.betweenness({nodeLabels:$labels, relationshipTypes:$rels}) YIELD node, score
WHERE score > 0
RETURN node.id AS id, labels(node)[0] AS label, coalesce(node.name, node.id) AS name, score
ORDER BY score DESC LIMIT 8
```

## `COMMUNITIES`



**Parameters:** none  
**Used by:** —

```cypher
CALL algo.labelPropagation({nodeLabels:['Person', 'Project', 'Item', 'Customer'],
                            relationshipTypes:['OWNS', 'WORKS_ON', 'LEADS', 'COVERS']})
YIELD node, communityId
OPTIONAL MATCH (node)-[:MEMBER_OF]->(t:Team)
RETURN communityId AS community, collect(node.id) AS members, collect(DISTINCT t.name) AS teams,
       collect(CASE WHEN node:Person THEN node.name END) AS people
```

## `SUPPLIERS_PER_PART`



**Parameters:** `$today`  
**Used by:** —

```cypher
MATCH (i:Item {kind:'part'})
OPTIONAL MATCH (s:Supplier)-[:QUOTED]->(q:Quote)-[:FOR]->(i) WHERE q.valid_until >= $today
RETURN i.id AS id, i.name AS name, count(DISTINCT s) AS suppliers
```

## `ORDER_VALUE_BY_REVISION`



**Parameters:** none  
**Used by:** —

```cypher
MATCH (o:Order)-[:FULFILLED_BY]->(:Build)-[:BUILDS]->(r:Revision)
RETURN r.id AS revision, sum(coalesce(o.unit_price, 0) * o.qty) AS value, collect(DISTINCT o.id) AS orders
```

## `KNOWLEDGE_SUBJECTS`



**Parameters:** none  
**Used by:** —

```cypher
MATCH (x) WHERE (x:Item AND x.kind IN ['part', 'assembly', 'firmware', 'test']) OR x:Project OR x:Customer
RETURN x.id AS id, labels(x)[0] AS label
```

## `LOAD`



**Parameters:** `$today`  
**Used by:** —

```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)<-[:ASSIGNED_TO]-(a:Action) WHERE coalesce(a.status, 'open') <> 'done'
OPTIONAL MATCH (p)-[:HAS_ABSENCE]->(ab:Absence) WHERE ab.end_date >= $today
RETURN p.id AS id, p.name AS name, count(DISTINCT a) AS open_tasks,
       collect(DISTINCT ab.start_date + ' → ' + ab.end_date) AS upcoming_absence
ORDER BY open_tasks DESC
```

## `SIGNALS`



**Parameters:** none  
**Used by:** —

```cypher
MATCH (s:Source) WHERE s.kind IN ['notice', 'escalation', 'leave']
OPTIONAL MATCH (s)<-[:PART_OF]-(c:Chunk)-[:MENTIONS]->(x)
OPTIONAL MATCH (inv:Investigation)-[:TRIGGERED_BY]->(s)
RETURN s.id AS id, s.kind AS kind, s.title AS title, max(c.ts) AS date,
       collect(DISTINCT {id: x.id, label: labels(x)[0]}) AS mentions, inv.id AS investigation
ORDER BY date DESC
```

# People and organisation

## `PERSON_CORE`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (p:Person {id:$id})
OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (t)-[:PART_OF]->(org:Organization)
OPTIONAL MATCH (p)-[:REPORTS_TO]->(m:Person)
OPTIONAL MATCH (r:Person)-[:REPORTS_TO]->(p)
OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p)
OPTIONAL MATCH (p)-[:BACKS_UP]->(c:Person)
OPTIONAL MATCH (p)-[hr:HOLDS_ROLE]->(o:Organization)
RETURN p.id AS id, p.name AS name, p.role AS role, t.id AS team_id, t.name AS team, org.name AS organization,
       m.id AS manager_id, m.name AS manager,
       collect(DISTINCT {id: r.id, name: r.name, role: r.role}) AS reports,
       collect(DISTINCT {id: b.id, name: b.name}) AS backed_up_by,
       collect(DISTINCT {id: c.id, name: c.name}) AS backs_up,
       collect(DISTINCT {role: hr.role, org: o.name}) AS org_roles
```

## `CHAIN`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH path = (:Person {id:$id})-[:REPORTS_TO*1..6]->(top:Person)
WITH path ORDER BY length(path) DESC LIMIT 1
RETURN [n IN nodes(path) | {id: n.id, name: n.name, role: n.role}] AS chain
```

## `WORK`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (:Person {id:$id})<-[:ASSIGNED_TO]-(a:Action)
OPTIONAL MATCH (a)-[:IN_PROJECT]->(pr:Project)
OPTIONAL MATCH (inv:Investigation)-[:PRODUCED]->(a)
OPTIONAL MATCH (a)-[:CONCERNS]->(t)
RETURN a.id AS id, a.title AS title, coalesce(a.status, 'open') AS status, a.kind AS kind,
       a.created_at AS created_at, a.completed_at AS completed_at, a.updated_at AS updated_at,
       pr.id AS project_id, pr.name AS project, inv.id AS investigation, inv.kind AS plan_kind, t.id AS target
ORDER BY coalesce(a.completed_at, a.updated_at, a.created_at) DESC
```

## `SKILLS`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (:Person {id:$id})-[:HAS_SKILL]->(s:Skill)
OPTIONAL MATCH (o:Person)-[:HAS_SKILL]->(s) WHERE o.id <> $id
RETURN s.id AS id, s.name AS name, collect(o.name) AS also
ORDER BY name
```

## `ABSENCES`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (:Person {id:$id})-[:HAS_ABSENCE]->(a:Absence)
RETURN a.start_date AS start_date, a.end_date AS end_date, a.kind AS kind, a.note AS note ORDER BY start_date
```

## `ORGS`



**Parameters:** none  
**Used by:** —

```cypher
MATCH (o:Organization)
OPTIONAL MATCH (o)-[:SUBSIDIARY_OF]->(parent:Organization)
OPTIONAL MATCH (p:Person)-[r:HOLDS_ROLE]->(o)
RETURN o.id AS id, o.name AS name, o.kind AS kind, o.note AS note, parent.id AS parent_id,
       collect(DISTINCT {id: p.id, name: p.name, role: r.role}) AS officers
```

## `TEAMS`



**Parameters:** none  
**Used by:** —

```cypher
MATCH (t:Team)
OPTIONAL MATCH (t)-[:PART_OF]->(o:Organization)
OPTIONAL MATCH (p:Person)-[:MEMBER_OF]->(t)
RETURN t.id AS id, t.name AS name, o.id AS org_id, collect(DISTINCT {id: p.id, name: p.name, role: p.role}) AS members
ORDER BY name
```

## `REPORTING`



**Parameters:** none  
**Used by:** —

```cypher
MATCH (p:Person)-[:REPORTS_TO]->(m:Person) RETURN p.id AS person, m.id AS manager
```

## `PEOPLE_FLAT`



**Parameters:** `$today`  
**Used by:** —

```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (p)<-[:ASSIGNED_TO]-(a:Action) WHERE coalesce(a.status, 'open') <> 'done'
OPTIONAL MATCH (p)-[:HAS_ABSENCE]->(ab:Absence) WHERE ab.start_date <= $today AND ab.end_date >= $today
RETURN p.id AS id, p.name AS name, p.role AS role, t.id AS team_id, t.name AS team,
       count(DISTINCT a) AS open_work, count(DISTINCT ab) > 0 AS away_now
```

## `MY_WATCH`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (me:Person {id:$id})
OPTIONAL MATCH (me)-[:OWNS]->(o)
OPTIONAL MATCH (me)-[:WORKS_ON|LEADS]->(pr:Project)
OPTIONAL MATCH (pr)-[:COVERS]->(x)
WITH me, collect(DISTINCT o.id) + collect(DISTINCT pr.id) + collect(DISTINCT x.id) AS ids
RETURN [i IN ids WHERE i IS NOT NULL] AS ids
```

## `MY_NEWS`



**Parameters:** `$ids`, `$since`  
**Used by:** —

```cypher
MATCH (c:Chunk)-[:MENTIONS]->(x) WHERE x.id IN $ids AND c.ts >= $since AND c.retracted_at IS NULL AND NOT c.text STARTS WITH '#'
MATCH (c)-[:PART_OF]->(s:Source)
RETURN DISTINCT c.id AS chunk, s.title AS title, s.kind AS kind, c.author AS author, c.ts AS ts, c.text AS text,
       collect(DISTINCT x.id) AS about
ORDER BY ts DESC LIMIT 12
```

## `TEAM_AWAY`



**Parameters:** `$id`, `$today`  
**Used by:** —

```cypher
MATCH (me:Person {id:$id})
OPTIONAL MATCH (me)-[:MEMBER_OF]->(t:Team)<-[:MEMBER_OF]-(colleague:Person)
OPTIONAL MATCH (r:Person)-[:REPORTS_TO*1..4]->(me)
WITH collect(DISTINCT colleague) + collect(DISTINCT r) AS people
UNWIND people AS p
MATCH (p)-[:HAS_ABSENCE]->(a:Absence) WHERE a.end_date >= $today
RETURN DISTINCT p.id AS id, p.name AS name, a.start_date AS start_date, a.end_date AS end_date
ORDER BY start_date
```

# Hybrid search

## `VECTOR`



**Parameters:** `$k`, `$v`  
**Used by:** —

```cypher
CALL db.idx.vector.queryNodes('Chunk', 'embedding', $k, vecf32($v)) YIELD node, score
RETURN node.id AS chunk, score
```

## `KEYWORD`



**Parameters:** `$k`, `$q`  
**Used by:** —

```cypher
CALL db.idx.fulltext.queryNodes('Chunk', $q) YIELD node, score
RETURN node.id AS chunk, score LIMIT $k
```

## `EXPAND`



**Parameters:** `$ids`  
**Used by:** —

```cypher
MATCH (c:Chunk) WHERE c.id IN $ids
MATCH (c)-[:PART_OF]->(s:Source)
OPTIONAL MATCH (c)-[:MENTIONS]->(x) WHERE NOT x:Source
RETURN c.id AS chunk, c.text AS text, c.author AS author, c.ts AS ts, c.page AS page, s.title AS title, s.kind AS kind,
       collect(DISTINCT {id: x.id, label: labels(x)[0]}) AS mentions
```

# Conversation memory

## `RECALL`

Past turns about a record or matching words, across everyone's conversations (shared memory).

**Parameters:** `$text`  
**Used by:** —

```cypher
MATCH (t:Turn)-[:ABOUT]->(x) WHERE x.id = $text OR toLower(coalesce(x.name, '')) = toLower($text)
MATCH (c:Conversation)-[:HAS_TURN]->(t)
OPTIONAL MATCH (p:Person)-[:STARTED]->(c)
RETURN t.question AS question, t.answer AS answer, t.at AS at, p.name AS asked_by
ORDER BY at DESC LIMIT 5
```

# Permissions

## `VIEWER`



**Parameters:** `$id`  
**Used by:** —

```cypher
MATCH (p:Person {id:$id})
OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (r:Person)-[:REPORTS_TO*1..6]->(p)
OPTIONAL MATCH (p)-[:BACKS_UP]->(covered:Person)
RETURN p.id AS id, p.name AS name, p.role AS role, t.id AS team, t.name AS team_name,
       collect(DISTINCT r.id) AS reports, collect(DISTINCT covered.id) AS covers
```
