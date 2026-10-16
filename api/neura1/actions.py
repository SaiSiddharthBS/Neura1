"""Investigations and approved actions, persisted in the graph.

Keys are content hashes, so approving the same task twice, or reopening the same notice in a
new session, finds the existing records instead of creating duplicates.
"""

import hashlib
import json
from datetime import datetime, timezone

from falkordb import Graph

from neura1.graph import rows


def _key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:10]


def investigation_id(item_id: str, source_id: str | None) -> str:
    return "INV-" + _key(item_id, source_id or "manual")


def find_investigation(graph: Graph, item_id: str, source_id: str | None) -> dict | None:
    found = rows(graph, """
        MATCH (inv:Investigation {id:$id})
        OPTIONAL MATCH (inv)-[:PRODUCED]->(a:Action)
        OPTIONAL MATCH (a)-[:ASSIGNED_TO]->(p:Person)
        RETURN inv.id AS id, inv.created_at AS created_at, inv.approved_by AS approved_by,
               inv.cost_total AS cost_total, inv.currency AS currency, inv.snapshot AS snapshot,
               collect(CASE WHEN a IS NULL THEN NULL ELSE
                 {id: a.id, kind: a.kind, title: a.title, status: a.status, owner: p.name,
                  created_at: a.created_at} END) AS actions
    """, {"id": investigation_id(item_id, source_id)})
    if not found:
        return None
    inv = found[0]
    inv["actions"] = [a for a in inv["actions"] if a]
    inv["snapshot"] = json.loads(inv["snapshot"]) if inv["snapshot"] else None
    return inv


def snapshot_of(report: dict) -> dict:
    """The facts an approval relied on, so later changes can be shown as a diff."""
    cost = report.get("cost") or {}
    return {
        "cost_total": str(cost.get("total_delta")) if cost else None,
        "baseline_quote": cost.get("baseline_quote"),
        "alternates": {a["id"]: a["status"] for a in report.get("alternates", [])},
        "alternate_quotes": {a["id"]: [q["id"] for q in a.get("quotes", [])] for a in report.get("alternates", [])},
        "builds_at_risk": sorted(b["build"] for b in report.get("builds", []) if b["at_risk"]),
        "revisions": sorted(u["revision"] for u in report.get("where_used", []) if u["applicable"]),
        "decisions": sorted(d["id"] for d in report.get("decisions", [])),
    }


def approve(graph: Graph, item_id: str, source_id: str | None, actions: list[dict], approved_by: str,
            cost_total: str | None, currency: str | None, snapshot: dict | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inv_id = investigation_id(item_id, source_id)
    graph.query("""
        MERGE (inv:Investigation {id:$id})
        ON CREATE SET inv.created_at=$now, inv.approved_by=$by, inv.cost_total=$cost, inv.currency=$cur,
                      inv.snapshot=$snap
        WITH inv MATCH (i:Item {id:$item}) MERGE (inv)-[:CONCERNS]->(i)
        WITH inv OPTIONAL MATCH (s:Source {id:$src})
        FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END | MERGE (inv)-[:TRIGGERED_BY]->(s))
    """, {"id": inv_id, "now": now, "by": approved_by, "cost": cost_total, "cur": currency,
          "item": item_id, "src": source_id, "snap": json.dumps(snapshot) if snapshot else None})

    created, existing = [], []
    for a in actions:
        action_id = "ACT-" + _key(inv_id, a["kind"], a["target"])
        res = rows(graph, """
            MATCH (inv:Investigation {id:$inv})
            MERGE (a:Action {id:$id})
            ON CREATE SET a.kind=$a.kind, a.target=$a.target, a.title=$a.title, a.why=$a.why,
                          a.status='open', a.created_at=$now, a.approved_by=$by, a.new=true
            ON MATCH SET a.new=false
            MERGE (inv)-[:PRODUCED]->(a)
            WITH a OPTIONAL MATCH (p:Person {name:$a.owner})
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (a)-[:ASSIGNED_TO]->(p))
            WITH a OPTIONAL MATCH (t {id:$a.target}) WHERE NOT t:Action
            FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | MERGE (a)-[:CONCERNS]->(t))
            WITH a UNWIND (CASE WHEN size($cites) = 0 THEN [NULL] ELSE $cites END) AS cid
            OPTIONAL MATCH (c:Chunk {id:cid})
            FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
                     MERGE (a)-[r:CITES]->(c) SET r.source_version=c.source_version)
            RETURN DISTINCT a.new AS new
        """, {"inv": inv_id, "id": action_id, "a": a, "now": now, "by": approved_by,
              "cites": a.get("cites", [])}, read_only=False)
        (created if res and res[0]["new"] else existing).append(action_id)
    return {"investigation": inv_id, "created": created, "already_existed": existing}
