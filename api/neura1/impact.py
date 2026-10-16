"""Change impact: one supplier change, traced through the company graph.

Graph traversal (FalkorDB) finds what is connected. Deterministic code does the arithmetic,
the stock and schedule checks, and the policy-driven task list. No model is called here.
"""

import time
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal

from falkordb import Graph

from neura1 import queries as Q
from neura1.engine.cost import CostError, Demand, OneTimeCost, Quote, price_change_scenario
from neura1.graph import rows

REQUAL_COST = OneTimeCost("TP-PSU-07 requalification (per candidate part)", Decimal(8000), "INR",
                          "docs/TP-PSU-07_test_procedure.md")


@dataclass
class ChangeEvent:
    item: str                      # part id or manufacturer part number as written in the notice
    new_unit_price: Decimal | None
    currency: str
    effective_date: date | None
    lead_weeks: int | None
    as_of: date
    source_id: str | None = None   # the notice this came from, if any


class Trace:
    """Records every Cypher statement run, so the UI can show exactly how an answer was built."""

    def __init__(self, graph: Graph):
        self.graph, self.steps = graph, []

    def run(self, name: str, query: str, params: dict) -> list[dict]:
        t0 = time.perf_counter()
        out = rows(self.graph, query, params)
        self.steps.append({"name": name, "cypher": query.strip(), "params": params,
                           "rows": len(out), "ms": round((time.perf_counter() - t0) * 1000, 1)})
        return out


def _d(s: str) -> date:
    return date.fromisoformat(s)


def alternate_status(decisions: list[dict]) -> str:
    """Only recorded decisions change an alternate's status; a cross-reference never does."""
    outcomes = {d["outcome"] for d in decisions if d.get("status") != "superseded"}
    if "approved" in outcomes and any(d["authority"] == "approved" for d in decisions):
        return "approved"
    if "rejected" in outcomes:
        return "rejected"
    if "proposed" in outcomes or "evidence" in outcomes:
        return "pending_review"
    return "unqualified"


def build_coverage(exposure: list[dict], qty_by_rev: dict[str, int], free_stock: int,
                   change: ChangeEvent) -> list[dict]:
    """Allocate free stock to builds in date order and flag builds that new supply cannot reach in time."""
    eta = change.as_of + timedelta(weeks=change.lead_weeks) if change.lead_weeks else None
    remaining, out = free_stock, []
    for b in exposure:
        need = b["build_qty"] * qty_by_rev[b["revision"]]
        from_stock = min(need, remaining)
        remaining -= from_stock
        short = need - from_stock
        planned = _d(b["planned_date"])
        out.append(b | {
            "parts_needed": need, "from_stock": from_stock, "shortfall": short,
            "supply_eta_if_ordered_today": eta.isoformat() if eta else None,
            "at_risk": bool(short and eta and eta > planned),
            "orders": [o for o in b["orders"] if o],
        })
    return out


def derive_actions(part: dict, parents: list[dict], dependents: list[dict], builds: list[dict],
                   policy: dict | None) -> list[dict]:
    """Tasks required by the change policy (HB-ENG-04), assigned to the owners recorded in the graph."""
    cite = [policy["chunk"]] if policy else []
    actions = []
    for p in parents:
        actions.append({"kind": "engineering_review", "target": p["item"], "owner": p["owner"],
                        "title": f"Engineering change review for {p['item']} ({', '.join(p['revisions'])})",
                        "why": "Component change on a released revision (HB-ENG-04 clause 1)", "cites": cite})
    for d in dependents:
        kind = {"firmware": "firmware_review", "test": "requalification"}.get(d["kind"], "review")
        clause = "3" if kind == "firmware_review" else "4"
        actions.append({"kind": kind, "target": d["id"], "owner": d["owner"],
                        "title": f"{'Firmware review' if kind == 'firmware_review' else 'Requalify'}: {d['name']}",
                        "why": f"{d['note']} (HB-ENG-04 clause {clause})",
                        "cites": cite + [e["chunk"] for e in d["evidence"] if e.get("chunk")]})
    actions.append({"kind": "procurement", "target": part["id"], "owner": part.get("owner"),
                    "title": f"Confirm pricing, MOQ, lead time and last-time-buy for {part['id']}",
                    "why": "HB-ENG-04 clause 5", "cites": cite})
    for b in [b for b in builds if b["at_risk"]]:
        actions.append({"kind": "production_replan", "target": b["build"], "owner": b["planner"],
                        "title": f"Replan {b['build']}: short {b['shortfall']} parts before {b['planned_date']}",
                        "why": "HB-ENG-04 clause 6", "cites": cite})
        for o in b["orders"]:
            actions.append({"kind": "customer_comms", "target": o["order"], "owner": o["account_manager"],
                            "title": f"Prepare {o['customer']} for possible change to {o['order']} (due {o['due']})",
                            "why": "HB-ENG-04 clause 6" + (f". {o['penalty']}" if o["penalty"] else ""),
                            "cites": cite})
    return actions


def analyse(graph: Graph, change: ChangeEvent) -> dict:
    t = Trace(graph)
    found = t.run("resolve_item", Q.RESOLVE_ITEM, {"text": change.item})
    if len(found) != 1:
        suggestions = found or (t.run("suggest_items", Q.SUGGEST_ITEMS, {"text": change.item.strip()})
                                if len(change.item.strip()) >= 3 else [])
        return {"status": "unresolved", "item": change.item, "candidates": suggestions, "trace": t.steps}
    part = found[0]
    pid = part["id"]
    owner = t.run("owners", "MATCH (p:Person)-[:OWNS]->(:Item {id:$id}) RETURN p.name AS name", {"id": pid})
    part["owner"] = owner[0]["name"] if owner else None

    used = t.run("where_used", Q.WHERE_USED, {"item_id": pid})
    applicable = [u for u in used if u["applicable"]]
    qty_by_rev = {u["revision"]: u["qty_per_unit"] for u in applicable}
    revs = list(qty_by_rev)
    path_revs = sorted({n for u in applicable for p in u["paths"] for n in p["nodes"] if n != pid})

    exposure = t.run("exposure", Q.EXPOSURE, {"revisions": revs})
    field_units = t.run("field_units", Q.FIELD_UNITS, {"item_id": pid})
    dependents = t.run("dependents", Q.DEPENDENTS, {"item_id": pid})
    parents = t.run("direct_parents", Q.DIRECT_PARENTS, {"item_id": pid, "revisions": path_revs})
    quotes = t.run("quotes", Q.QUOTES, {"item_id": pid})
    alternates = t.run("alternates", Q.ALTERNATES, {"item_id": pid})
    decisions = t.run("decisions", Q.DECISIONS, {"item_id": pid})
    for d in decisions:  # the passage that states the decision first, then supporting results
        d["evidence"] = sorted([e for e in d["evidence"] if e.get("chunk")], key=lambda e: e.get("rank") or 0)
    policy = (t.run("policy", Q.POLICY_CHUNK, {"ref": "HB-ENG-04"}) or [None])[0]

    for a in alternates:
        a["quotes"] = t.run("alternate_quotes", Q.QUOTES, {"item_id": a["id"]})
        a["decisions"] = [d for d in decisions if d["subject"] == a["id"]]
        a["status"] = alternate_status(a["decisions"])

    free = max((part["on_hand"] or 0) - (part["allocated"] or 0), 0)
    builds = build_coverage(exposure, qty_by_rev, free, change)

    cost, cost_error = None, None
    try:
        scenario = price_change_scenario(
            demand=[Demand(b["build"], b["revision"], b["build_qty"], qty_by_rev[b["revision"]]) for b in exposure],
            on_hand=part["on_hand"] or 0, allocated=part["allocated"] or 0,
            quotes=[Quote(q["id"], Decimal(q["unit_price"]), q["currency"], q["moq"], _d(q["valid_from"]),
                          _d(q["valid_until"]), q["lead_weeks"]) for q in quotes],
            new_unit_price=change.new_unit_price, new_currency=change.currency, as_of=change.as_of,
            one_time=[REQUAL_COST] if dependents else [],
        )
        cost = asdict(scenario)
    except CostError as exc:
        cost_error = str(exc)

    return {
        "status": "ok",
        "change": asdict(change),
        "part": part,
        "where_used": used,
        "builds": builds,
        "field_units": field_units,
        "dependents": dependents,
        "assemblies": parents,
        "quotes": quotes,
        "alternates": alternates,
        "decisions": decisions,
        "cost": cost,
        "cost_error": cost_error,
        "actions": derive_actions(part, parents, dependents, builds, policy),
        "assumptions": ["No open purchase orders are recorded for this part",
                        "Allocated stock is reserved for other demand and is not available to these builds"],
        "trace": t.steps,
    }
