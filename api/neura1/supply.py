"""Supply facts shared by "Can we promise this?" and the company sandbox.

All arithmetic is code. Lead times come from the newest information on record: a supplier notice beats a quote, because
a notice is what changed after the quote was issued (the NB54360 quote says 6 weeks; the 14 October notice says 22).
"""

import json
from datetime import date, timedelta

from falkordb import Graph

from neura1.graph import rows

REV_TEXT = """
MATCH (i:Item)-[:HAS_REV]->(r:Revision) WHERE toUpper(r.id) = toUpper($t)
RETURN r.id AS id, r.status AS status, i.id AS item
UNION
MATCH (i:Item {kind:'product'})-[:HAS_REV]->(r:Revision)
WHERE toUpper(i.id) = toUpper($t) OR toUpper(i.id + ' REV ' + r.rev) = toUpper($t)
RETURN r.id AS id, r.status AS status, i.id AS item
"""

EXPLODE = """
MATCH p = (top:Revision {id:$rev})-[:CONTAINS*1..8]->(part:Item) WHERE part.kind = 'part'
WITH part, reduce(q = 1, r IN relationships(p) | q * r.qty) AS qty
RETURN part.id AS id, part.name AS name, sum(qty) AS per_unit,
       coalesce(part.on_hand, -1) AS on_hand, coalesce(part.allocated, 0) AS allocated
ORDER BY id
"""

VALID_QUOTES = """
MATCH (s:Supplier)-[:QUOTED]->(q:Quote)-[:FOR]->(:Item {id:$id})
WHERE (q.valid_from IS NULL OR q.valid_from <= $today) AND (q.valid_until IS NULL OR q.valid_until >= $today)
RETURN q.id AS id, s.name AS supplier, q.unit_price AS price, q.moq AS moq, q.lead_weeks AS lead_weeks,
       q.valid_until AS valid_until
ORDER BY lead_weeks
"""

# What the open builds will take of a part, by build.
DEMAND = """
MATCH (b:Build)-[:BUILDS]->(r:Revision)
WHERE coalesce(b.status, 'planned') <> 'done'
MATCH p = (r)-[:CONTAINS*1..8]->(:Item {id:$id})
WITH b, r, reduce(q = 1, x IN relationships(p) | q * x.qty) AS qty
WITH b, r, sum(qty) AS per_unit
RETURN b.id AS build, r.id AS revision, b.planned_date AS planned_date, b.qty AS units, per_unit, per_unit * b.qty AS need
ORDER BY planned_date
"""

# How long recent orders for a part actually took, from order to goods received.
ORDER_HISTORY = """
MATCH (g:Receipt)-[:AGAINST]->(po:PurchaseOrder)-[:ORDERS]->(:Item {id:$id})
OPTIONAL MATCH (po)-[:FROM_SUPPLIER]->(s:Supplier)
RETURN po.id AS id, po.ordered_on AS ordered_on, min(g.received_on) AS received_on, s.name AS supplier
ORDER BY ordered_on DESC LIMIT 3
"""

ALTERNATES = """
MATCH (a:Item)-[r:ALTERNATE_OF]->(:Item {id:$id})
OPTIONAL MATCH (d:Decision)-[:ABOUT]->(a) WHERE coalesce(d.status, 'active') = 'active'
RETURN a.id AS id, r.note AS note, collect(DISTINCT {id: d.id, outcome: d.outcome, reason: d.reason}) AS decisions
"""


def resolve_revision(graph: Graph, text: str) -> list[dict]:
    """A product (its released revision), a revision id, or "PDU-28 Rev C"."""
    found = {r["id"]: r for r in rows(graph, REV_TEXT, {"t": text.strip()})}.values()
    found = list(found)
    released = [r for r in found if r["status"] == "released"]
    exact = [r for r in found if r["id"].upper() == text.strip().upper()]
    return exact or (released if len(released) == 1 else found)


def explode(graph: Graph, revision: str) -> list[dict]:
    return rows(graph, EXPLODE, {"rev": revision})


def notices(graph: Graph) -> dict[str, dict]:
    """The newest verified supplier notice per part: price, lead time, last-time-buy, and where it came from."""
    from neura1 import scenarios
    from neura1.ingest import extract
    out: dict[str, dict] = {}
    for s in scenarios.signals(graph):
        if s["kind"] != "notice":
            continue
        path = extract.snapshot_path(s["id"], "notice")
        if not path.exists():
            continue
        snap = extract.with_resolved_part(graph, json.loads(path.read_text()))
        o = snap.get("output") or {}
        part = o.get("part")
        if part and (part not in out or (s.get("date") or "") > out[part].get("received", "")):
            out[part] = {"source": s["id"], "received": s.get("date") or "", "lead_weeks": o.get("lead_weeks"),
                         "new_unit_price": o.get("new_unit_price"), "effective_date": o.get("effective_date"),
                         "last_time_buy": o.get("last_time_buy"), "changes": o.get("change_types") or []}
    return out


def lead_time(graph: Graph, item: str, today: date, notice: dict | None) -> dict:
    """How long new supply takes, by the newest information: a notice, else the shortest valid quote, else unknown."""
    quotes = rows(graph, VALID_QUOTES, {"id": item, "today": today.isoformat()})
    quote = quotes[0] if quotes else None
    if notice and notice.get("lead_weeks"):
        return {"weeks": int(notice["lead_weeks"]), "basis": "notice", "source": notice["source"], "quote": quote,
                "quote_weeks": quote["lead_weeks"] if quote else None}
    if quote and quote["lead_weeks"] is not None:
        return {"weeks": int(quote["lead_weeks"]), "basis": "quote", "source": quote["id"], "quote": quote,
                "quote_weeks": quote["lead_weeks"]}
    past = [h for h in rows(graph, ORDER_HISTORY, {"id": item}) if h["received_on"] and h["ordered_on"]]
    if past:  # no quote or notice: how long the last orders actually took
        days = [(date.fromisoformat(h["received_on"]) - date.fromisoformat(h["ordered_on"])).days for h in past]
        return {"weeks": -(-max(days) // 7), "basis": "history", "source": past[0]["id"], "quote": None,
                "quote_weeks": None, "supplier": past[0]["supplier"]}
    return {"weeks": None, "basis": "unknown", "source": None, "quote": None, "quote_weeks": None}


def planned_need(graph: Graph, item: str) -> int:
    """Parts the open builds will use. Free stock goes to them first, before any new order."""
    return int(sum(d["need"] or 0 for d in rows(graph, DEMAND, {"id": item})))


def alternates(graph: Graph, item: str, today: date) -> list[dict]:
    out = []
    for a in rows(graph, ALTERNATES, {"id": item}):
        decided = [d for d in a["decisions"] if d.get("id")]
        status = "rejected" if any(d["outcome"] == "rejected" for d in decided) else \
            "approved" if any(d["outcome"] == "approved" for d in decided) else "not qualified"
        quotes = rows(graph, VALID_QUOTES, {"id": a["id"], "today": today.isoformat()})
        out.append({"id": a["id"], "note": a["note"], "status": status, "decisions": decided,
                    "quote": quotes[0] if quotes else None})
    return out


def weeks(d: date, n: int) -> date:
    return d + timedelta(weeks=n)
