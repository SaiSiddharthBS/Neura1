"""Load system-of-record CSV exports into FalkorDB.

Every write is a MERGE keyed on a stable id, so re-running the import is idempotent.
Every node and relationship carries `source` (which export it came from) and
`authority = 'system_of_record'` so it can be told apart from LLM-extracted claims.
"""

import csv
from pathlib import Path

from falkordb import Graph

from neura1.config import settings

SOR = "system_of_record"


class BomCycleError(ValueError):
    pass


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        out = []
        for line, row in enumerate(csv.DictReader(f), start=2):
            if None in row:
                raise ValueError(f"{path.name} line {line}: more values than columns (quote values that contain commas)")
            out.append({k: (v.strip() if v is not None else v) for k, v in row.items()})
        return out


def check_bom_cycles(bom: list[dict]) -> None:
    """Reject the import if any revision transitively contains itself."""
    children: dict[str, list[str]] = {}
    for line in bom:
        if line["child_rev"]:
            children.setdefault(line["parent_rev"], []).append(line["child_rev"])

    WHITE, GREY, BLACK = 0, 1, 2
    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> None:
        state[node] = GREY
        for child in children.get(node, []):
            if state.get(child, WHITE) == GREY:
                raise BomCycleError(" -> ".join(path + [node, child]))
            if state.get(child, WHITE) == WHITE:
                visit(child, path + [node])
        state[node] = BLACK

    for node in list(children):
        if state.get(node, WHITE) == WHITE:
            visit(node, [])


INDEXES = [
    "CREATE INDEX FOR (n:Item) ON (n.id)",
    "CREATE INDEX FOR (n:Item) ON (n.mpn)",
    "CREATE INDEX FOR (n:Revision) ON (n.id)",
    "CREATE INDEX FOR (n:Person) ON (n.id)",
    "CREATE INDEX FOR (n:Team) ON (n.id)",
    "CREATE INDEX FOR (n:Build) ON (n.id)",
    "CREATE INDEX FOR (n:Order) ON (n.id)",
    "CREATE INDEX FOR (n:Customer) ON (n.id)",
    "CREATE INDEX FOR (n:Supplier) ON (n.id)",
    "CREATE INDEX FOR (n:Quote) ON (n.id)",
    "CREATE INDEX FOR (n:Source) ON (n.id)",
    "CREATE INDEX FOR (n:Decision) ON (n.id)",
    "CREATE INDEX FOR (n:Project) ON (n.id)",
    "CREATE INDEX FOR (n:Alias) ON (n.term)",
    "CREATE INDEX FOR (n:Certification) ON (n.id)",
    "CREATE INDEX FOR (n:Organization) ON (n.id)",
    "CREATE INDEX FOR (n:Skill) ON (n.name)",
    "CREATE INDEX FOR (n:Action) ON (n.id)",
    "CREATE INDEX FOR (n:PurchaseOrder) ON (n.id)",
    "CREATE INDEX FOR (n:Receipt) ON (n.id)",
    "CREATE INDEX FOR (n:StockMove) ON (n.id)",
]

# (csv file, cypher). Each row is passed as $r; $src is the export's source id.
LOADERS: list[tuple[str, str]] = [
    ("organizations.csv", """
        MERGE (o:Organization {id:$r.id})
        SET o.name=$r.name, o.kind=$r.kind, o.note=$r.note, o.source=$src, o.authority=$auth
        WITH o OPTIONAL MATCH (parent:Organization {id:$r.parent_id})
        FOREACH (_ IN CASE WHEN parent IS NULL THEN [] ELSE [1] END | MERGE (o)-[:SUBSIDIARY_OF]->(parent))"""),
    ("teams.csv", """
        MERGE (t:Team {id:$r.id}) SET t.name=$r.name, t.source=$src, t.authority=$auth
        WITH t OPTIONAL MATCH (o:Organization {id:$r.org_id})
        FOREACH (_ IN CASE WHEN o IS NULL THEN [] ELSE [1] END | MERGE (t)-[:PART_OF]->(o))"""),
    ("people.csv", """
        MERGE (p:Person {id:$r.id}) SET p.name=$r.name, p.role=$r.role, p.source=$src, p.authority=$auth
        WITH p MATCH (t:Team {id:$r.team_id}) MERGE (p)-[m:MEMBER_OF]->(t) SET m.source=$src"""),
    ("items.csv", """
        MERGE (i:Item {id:$r.id})
        SET i.kind=$r.kind, i.name=$r.name, i.mpn=$r.mpn, i.manufacturer=$r.manufacturer,
            i.source=$src, i.authority=$auth"""),
    ("revisions.csv", """
        MERGE (v:Revision {id:$r.id})
        SET v.rev=$r.rev, v.status=$r.status, v.effective_from=$r.effective_from, v.source=$src, v.authority=$auth
        WITH v MATCH (i:Item {id:$r.item_id}) MERGE (i)-[h:HAS_REV]->(v) SET h.source=$src"""),
    # A BOM line points at the pinned child revision for assemblies, or at the part item otherwise.
    ("bom.csv", """
        MATCH (parent:Revision {id:$r.parent_rev})
        OPTIONAL MATCH (crev:Revision {id:$r.child_rev})
        OPTIONAL MATCH (citem:Item {id:$r.child_item})
        WITH parent, CASE WHEN $r.child_rev <> '' THEN crev ELSE citem END AS child
        MERGE (parent)-[c:CONTAINS {refdes:$r.refdes}]->(child)
        SET c.qty=toInteger($r.qty), c.uom=$r.uom, c.child_item=$r.child_item, c.source=$src, c.authority=$auth"""),
    ("alternates.csv", """
        MATCH (a:Item {id:$r.item_id}), (b:Item {id:$r.alt_item_id})
        MERGE (b)-[x:ALTERNATE_OF]->(a) SET x.basis=$r.basis, x.note=$r.note, x.source=$src, x.authority=$auth"""),
    ("dependencies.csv", """
        MATCH (a:Item {id:$r.from_item}), (b:Item {id:$r.to_item})
        MERGE (a)-[d:DEPENDS_ON]->(b) SET d.note=$r.note, d.source=$src, d.authority=$auth"""),
    ("suppliers.csv", "MERGE (s:Supplier {id:$r.id}) SET s.name=$r.name, s.source=$src, s.authority=$auth"),
    ("quotes.csv", """
        MERGE (q:Quote {id:$r.id})
        SET q.unit_price=$r.unit_price, q.currency=$r.currency, q.moq=toInteger($r.moq),
            q.lead_weeks=toInteger($r.lead_weeks), q.valid_from=$r.valid_from, q.valid_until=$r.valid_until,
            q.source=$src, q.authority=$auth
        WITH q MATCH (s:Supplier {id:$r.supplier_id}), (i:Item {id:$r.item_id})
        MERGE (s)-[:QUOTED]->(q) MERGE (q)-[:FOR]->(i)"""),
    ("stock.csv", """
        MATCH (i:Item {id:$r.item_id})
        SET i.on_hand=toInteger($r.on_hand), i.allocated=toInteger($r.allocated), i.stock_source=$src"""),
    ("item_details.csv", """
        MATCH (i:Item {id:$r.item_id})
        SET i.category=$r.category, i.uom=$r.uom, i.hsn=$r.hsn, i.reorder_level=toInteger($r.reorder_level),
            i.location=$r.location"""),
    # Purchasing and stores: every order placed, every delivery received, and every movement of stock.
    ("purchase_orders.csv", """
        MERGE (po:PurchaseOrder {id:$r.id})
        SET po.qty=toInteger($r.qty), po.unit_price=$r.unit_price, po.currency=$r.currency, po.ordered_on=$r.ordered_on,
            po.expected_on=$r.expected_on, po.status=$r.status, po.source=$src, po.authority=$auth
        WITH po MATCH (s:Supplier {id:$r.supplier_id}), (i:Item {id:$r.item_id})
        MERGE (po)-[:FROM_SUPPLIER]->(s) MERGE (po)-[:ORDERS]->(i)
        WITH po OPTIONAL MATCH (q:Quote {id:$r.quote_id})
        FOREACH (_ IN CASE WHEN q IS NULL THEN [] ELSE [1] END | MERGE (po)-[:PRICED_BY]->(q))"""),
    ("receipts.csv", """
        MERGE (g:Receipt {id:$r.id})
        SET g.qty=toInteger($r.qty), g.received_on=$r.received_on, g.location=$r.location, g.lot=$r.lot,
            g.rejected=toInteger(coalesce($r.rejected, '0')), g.note=$r.note, g.source=$src, g.authority=$auth
        WITH g MATCH (po:PurchaseOrder {id:$r.po_id}), (i:Item {id:$r.item_id})
        MERGE (g)-[:AGAINST]->(po) MERGE (g)-[:RECEIVES]->(i)"""),
    ("stock_moves.csv", """
        MERGE (m:StockMove {id:$r.id})
        SET m.date=$r.date, m.qty=toInteger($r.qty), m.kind=$r.kind, m.ref=$r.ref, m.location=$r.location,
            m.note=$r.note, m.source=$src, m.authority=$auth
        WITH m MATCH (i:Item {id:$r.item_id}) MERGE (m)-[:MOVES]->(i)"""),
    ("customers.csv", "MERGE (c:Customer {id:$r.id}) SET c.name=$r.name, c.source=$src, c.authority=$auth"),
    ("builds.csv", """
        MERGE (b:Build {id:$r.id})
        SET b.qty=toInteger($r.qty), b.planned_date=$r.planned_date, b.status=$r.status, b.source=$src, b.authority=$auth
        WITH b MATCH (v:Revision {id:$r.rev_id}) MERGE (b)-[:BUILDS]->(v)"""),
    ("orders.csv", """
        MERGE (o:Order {id:$r.id})
        SET o.qty=toInteger($r.qty), o.due_date=$r.due_date, o.penalty_note=$r.penalty_note,
            o.unit_price=CASE WHEN coalesce($r.unit_price, '') = '' THEN NULL ELSE toFloat($r.unit_price) END,
            o.penalty_pct_per_week=CASE WHEN coalesce($r.penalty_pct_per_week, '') = '' THEN NULL
                                        ELSE toFloat($r.penalty_pct_per_week) END,
            o.penalty_cap_pct=CASE WHEN coalesce($r.penalty_cap_pct, '') = '' THEN NULL ELSE toFloat($r.penalty_cap_pct) END,
            o.source=$src, o.authority=$auth
        WITH o MATCH (c:Customer {id:$r.customer_id}), (b:Build {id:$r.build_id})
        MERGE (c)-[:PLACED]->(o) MERGE (o)-[:FULFILLED_BY]->(b)"""),
    ("shipments.csv", """
        MERGE (s:Shipment {id:$r.id})
        SET s.qty=toInteger($r.qty), s.shipped_on=$r.shipped_on, s.source=$src, s.authority=$auth
        WITH s MATCH (c:Customer {id:$r.customer_id}), (v:Revision {id:$r.rev_id})
        MERGE (s)-[:SHIPPED_TO]->(c) MERGE (s)-[:OF_REV]->(v)"""),
    ("projects.csv", """
        MERGE (p:Project {id:$r.id})
        SET p.name=$r.name, p.status=$r.status, p.start_date=$r.start_date, p.target_date=$r.target_date,
            p.summary=$r.summary, p.source=$src, p.authority=$auth
        WITH p MATCH (lead:Person {id:$r.lead_id}) MERGE (lead)-[l:LEADS]->(p) SET l.source=$src"""),
    ("project_members.csv", """
        MATCH (p:Project {id:$r.project_id}), (m:Person {id:$r.person_id})
        MERGE (m)-[w:WORKS_ON]->(p) SET w.role=$r.role, w.source=$src, w.authority=$auth"""),
    # A project covers any record: customers, orders, builds, revisions, items.
    ("project_scope.csv", """
        MATCH (p:Project {id:$r.project_id}), (x {id:$r.target_id})
        MERGE (p)-[c:COVERS]->(x) SET c.source=$src, c.authority=$auth"""),
    ("backups.csv", """
        MATCH (a:Person {id:$r.person_id}), (b:Person {id:$r.backup_id})
        MERGE (b)-[c:BACKS_UP]->(a) SET c.source=$src, c.authority=$auth"""),
    ("org_roles.csv", """
        MATCH (p:Person {id:$r.person_id}), (o:Organization {id:$r.org_id})
        MERGE (p)-[r:HOLDS_ROLE {role:$r.role}]->(o) SET r.source=$src, r.authority=$auth"""),
    ("skills.csv", """
        MATCH (p:Person {id:$r.person_id})
        MERGE (s:Skill {name:$r.skill}) ON CREATE SET s.id = 'SK-' + toUpper(replace($r.skill, ' ', '-'))
        MERGE (p)-[h:HAS_SKILL]->(s) SET h.source=$src, h.authority=$auth"""),
    # Work items exported from the company's tracker: what people are doing and have done.
    ("tasks.csv", """
        MERGE (a:Action {id:$r.id})
        SET a.kind='work', a.title=$r.title, a.status=$r.status, a.created_at=$r.created,
            a.completed_at=CASE WHEN coalesce($r.completed, '') = '' THEN NULL ELSE $r.completed END,
            a.target=$r.target_id, a.source=$src, a.authority=$auth
        WITH a OPTIONAL MATCH (p:Person {id:$r.assignee_id})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (a)-[:ASSIGNED_TO]->(p))
        WITH a OPTIONAL MATCH (pr:Project {id:$r.project_id})
        FOREACH (_ IN CASE WHEN pr IS NULL THEN [] ELSE [1] END | MERGE (a)-[:IN_PROJECT]->(pr))
        WITH a OPTIONAL MATCH (t {id:$r.target_id}) WHERE NOT t:Action
        FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | MERGE (a)-[:CONCERNS]->(t))"""),
    ("reports_to.csv", """
        MATCH (p:Person {id:$r.person_id}), (m:Person {id:$r.manager_id})
        MERGE (p)-[r:REPORTS_TO]->(m) SET r.source=$src, r.authority=$auth"""),
    ("absences.csv", """
        MATCH (p:Person {id:$r.person_id})
        MERGE (a:Absence {id:$r.person_id + ':' + $r.start_date})
        SET a.start_date=$r.start_date, a.end_date=$r.end_date, a.kind=$r.kind, a.note=$r.note,
            a.source=$src, a.authority=$auth
        MERGE (p)-[:HAS_ABSENCE]->(a)"""),
    ("certifications.csv", """
        MERGE (c:Certification {id:$r.id})
        SET c.name=$r.name, c.standard=$r.standard, c.status=$r.status, c.valid_until=$r.valid_until,
            c.source=$src, c.authority=$auth
        WITH c MATCH (r:Revision {id:$r.revision_id}) MERGE (c)-[:CERTIFIES]->(r)
        WITH c OPTIONAL MATCH (o:Person {id:$r.owner_id})
        FOREACH (_ IN CASE WHEN o IS NULL THEN [] ELSE [1] END | MERGE (o)-[:OWNS]->(c))
        WITH c OPTIONAL MATCH (t:Item {id:$r.retest_trigger_item})
        FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | MERGE (c)-[:RETEST_IF_CHANGED]->(t))"""),
    # Other names people use for a record in chats and documents (e.g. "pmic_seq.c" for FW-PMIC-SEQ).
    ("aliases.csv", """
        MATCH (x {id:$r.target_id})
        MERGE (a:Alias {term:$r.term}) MERGE (a)-[:REFERS_TO]->(x) SET a.source=$src"""),
    # Ownership targets can be any labelled node with an id.
    ("ownership.csv", """
        MATCH (p:Person {id:$r.person_id}), (x {id:$r.target_id})
        MERGE (p)-[o:OWNS]->(x) SET o.source=$src, o.authority=$auth"""),
]


def ensure_indexes(graph: Graph) -> None:
    for stmt in INDEXES:
        try:
            graph.query(stmt)
        except Exception as exc:
            if "already indexed" not in str(exc).lower():
                raise


def load_rows(graph: Graph, kind: str, data: list[dict], src: str) -> int:
    """Load already-validated rows of one record type (e.g. kind='bom')."""
    cypher = dict(LOADERS)[f"{kind}.csv"]
    graph.query(
        "MERGE (s:Source {id:$id}) SET s.kind='export', s.uri=$id, s.authority=$auth",
        {"id": src, "auth": SOR},
    )
    for r in data:
        graph.query(cypher, {"r": r, "src": src, "auth": SOR})
    return len(data)


def load_records(graph: Graph, records_dir: Path | None = None) -> dict[str, int]:
    records_dir = records_dir or settings.fixture_dir / "records"
    check_bom_cycles(read_csv(records_dir / "bom.csv"))
    ensure_indexes(graph)
    return {filename: load_rows(graph, filename.removesuffix(".csv"), read_csv(records_dir / filename),
                                f"records/{filename}")
            for filename, _ in LOADERS}


def existing_ids(graph: Graph) -> dict:
    """Ids already in the graph, by record type, so an import can reference them."""
    from neura1.graph import rows

    labels = {"teams": "Team", "people": "Person", "items": "Item", "revisions": "Revision",
              "suppliers": "Supplier", "quotes": "Quote", "customers": "Customer", "builds": "Build",
              "orders": "Order", "shipments": "Shipment", "projects": "Project",
              "certifications": "Certification", "organizations": "Organization", "tasks": "Action",
              "purchase_orders": "PurchaseOrder", "receipts": "Receipt", "stock_moves": "StockMove"}
    out: dict = {k: {r["id"] for r in rows(graph, f"MATCH (n:{label}) RETURN n.id AS id")}
                 for k, label in labels.items()}
    out["_mpn"] = {r["mpn"].upper(): r["id"] for r in rows(
        graph, "MATCH (i:Item) WHERE i.mpn IS NOT NULL AND i.mpn <> '' RETURN i.id AS id, i.mpn AS mpn")}
    out["_item_kind"] = {r["id"]: r["kind"] for r in rows(graph, "MATCH (i:Item) RETURN i.id AS id, i.kind AS kind")}
    out["_rev_status"] = {r["id"]: r["status"] for r in rows(
        graph, "MATCH (r:Revision) RETURN r.id AS id, r.status AS status")}
    out["_rev_item"] = {r["rev"]: r["item"] for r in rows(
        graph, "MATCH (i:Item)-[:HAS_REV]->(r:Revision) RETURN r.id AS rev, i.id AS item")}
    return out
