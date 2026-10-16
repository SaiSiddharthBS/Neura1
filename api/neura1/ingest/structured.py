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
        return [{k: (v.strip() if v is not None else v) for k, v in row.items()} for row in csv.DictReader(f)]


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
]

# (csv file, cypher). Each row is passed as $r; $src is the export's source id.
LOADERS: list[tuple[str, str]] = [
    ("teams.csv", "MERGE (t:Team {id:$r.id}) SET t.name=$r.name, t.source=$src, t.authority=$auth"),
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
    ("customers.csv", "MERGE (c:Customer {id:$r.id}) SET c.name=$r.name, c.source=$src, c.authority=$auth"),
    ("builds.csv", """
        MERGE (b:Build {id:$r.id})
        SET b.qty=toInteger($r.qty), b.planned_date=$r.planned_date, b.status=$r.status, b.source=$src, b.authority=$auth
        WITH b MATCH (v:Revision {id:$r.rev_id}) MERGE (b)-[:BUILDS]->(v)"""),
    ("orders.csv", """
        MERGE (o:Order {id:$r.id})
        SET o.qty=toInteger($r.qty), o.due_date=$r.due_date, o.penalty_note=$r.penalty_note, o.source=$src, o.authority=$auth
        WITH o MATCH (c:Customer {id:$r.customer_id}), (b:Build {id:$r.build_id})
        MERGE (c)-[:PLACED]->(o) MERGE (o)-[:FULFILLED_BY]->(b)"""),
    ("shipments.csv", """
        MERGE (s:Shipment {id:$r.id})
        SET s.qty=toInteger($r.qty), s.shipped_on=$r.shipped_on, s.source=$src, s.authority=$auth
        WITH s MATCH (c:Customer {id:$r.customer_id}), (v:Revision {id:$r.rev_id})
        MERGE (s)-[:SHIPPED_TO]->(c) MERGE (s)-[:OF_REV]->(v)"""),
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
              "orders": "Order", "shipments": "Shipment"}
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
