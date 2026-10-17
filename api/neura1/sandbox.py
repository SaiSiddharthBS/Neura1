"""Company sandbox: try a decision on a copy of the company before living with it.

FalkorDB copies the whole company graph in about a tenth of a second (GRAPH.COPY). A scenario's shocks are applied to
the copy, the same engines that run on the real company (change impact, a person away, stock and lead times) run on the
copy, and the copy is thrown away. The real graph is never written.

Each shock is also run alone, on its own copy. Whatever appears only when the shocks are combined is reported as such:
those are the risks no single analysis, meeting or spreadsheet would have shown. For example, a regulator change needs
a firmware review, and the one person who could do it is away in the same weeks.

Shocks:
  part      a supplier change: new price, new lead time, or end of life (no further supply)
  person    someone away for a period, or leaving the company
  order     a customer order scaled up or down (its build follows)
  supplier  a supplier that stops supplying (its quotes disappear)
"""

import time
import uuid
from datetime import date, timedelta
from decimal import Decimal

from falkordb import Graph

from neura1 import scenarios, supply
from neura1.graph import get_graph, rows
from neura1.impact import ChangeEvent, analyse

NO_SUPPLY_WEEKS = 520   # end of life, or nobody left quoting the part: no new supply within any plan
BUILD_WEEKS = 3

PRESETS = [
    {"id": "storm", "title": "The perfect storm",
     "description": "The NB54360 notice takes effect, Sai is away for November, and Konkan Naval doubles its order.",
     "shocks": [{"kind": "part", "item": "NB54360", "price": 320, "lead_weeks": 22},
                {"kind": "person", "person": "P-SAI", "start": "2026-11-02", "end": "2026-11-30"},
                {"kind": "order", "order": "SO-884", "factor": 2}]},
    {"id": "eol", "title": "NB54360 goes end of life",
     "description": "Northbridge stops making the regulator, and Deccan Components stops supplying Flyvi.",
     "shocks": [{"kind": "part", "item": "NB54360", "eol": True},
                {"kind": "supplier", "supplier": "S-DECCAN"}]},
    {"id": "leaves", "title": "A key engineer leaves",
     "description": "Raghavendra leaves Flyvi at the end of the month.",
     "shocks": [{"kind": "person", "person": "P-RAGHAVENDRA", "start": "2026-10-31", "end": None}]},
    {"id": "growth", "title": "Konkan Naval doubles its order",
     "description": "SO-884 goes from 60 to 120 BCU-24 units on the same date.",
     "shocks": [{"kind": "order", "order": "SO-884", "factor": 2}]},
]

ORDERS = """
MATCH (c:Customer)-[:PLACED]->(o:Order)
OPTIONAL MATCH (am:Person)-[:OWNS]->(c)
RETURN o.id AS id, c.name AS customer, am.id AS owner_id, am.name AS owner, o.qty AS qty, o.due_date AS due,
       coalesce(o.unit_price, 0) * coalesce(o.qty, 0) AS value, coalesce(o.penalty_cap_pct, 0) AS penalty_cap
"""

AWAY = """
MATCH (p:Person)-[:HAS_ABSENCE]->(a:Absence) WHERE a.end_date >= $from AND a.start_date <= $to
OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p)
RETURN p.id AS id, p.name AS name, a.start_date AS start, a.end_date AS end, a.kind AS kind, b.name AS backup
"""

BUILDS_OF_ORDER = """
MATCH (o:Order {id:$id})-[:FULFILLED_BY]->(b:Build)-[:BUILDS]->(r:Revision)
OPTIONAL MATCH (planner:Person)-[:OWNS]->(b)
RETURN b.id AS build, b.qty AS qty, b.planned_date AS planned_date, r.id AS revision, planner.id AS planner_id,
       planner.name AS planner
"""

QUOTED_PARTS = """
MATCH (q:Quote)-[:FOR]->(i:Item)
WHERE (q.valid_from IS NULL OR q.valid_from <= $today) AND (q.valid_until IS NULL OR q.valid_until >= $today)
RETURN DISTINCT i.id AS id
"""


class SandboxError(ValueError):
    pass


def _names(graph: Graph) -> dict[str, str]:
    return {r["id"]: r["name"] for r in rows(graph, "MATCH (n) WHERE n:Person OR n:Supplier OR n:Item "
                                                    "RETURN n.id AS id, n.name AS name")}


def describe(shock: dict, names: dict[str, str]) -> str:
    k = shock["kind"]
    if k == "part":
        if shock.get("eol"):
            return f"{shock['item']} goes end of life"
        bits = [f"price ₹{shock['price']:g}" if shock.get("price") else None,
                f"lead time {shock['lead_weeks']} weeks" if shock.get("lead_weeks") else None]
        return f"{shock['item']}: " + ", ".join(b for b in bits if b)
    if k == "person":
        who = names.get(shock["person"], shock["person"])
        return f"{who} leaves Flyvi from {shock['start']}" if not shock.get("end") else \
            f"{who} is away {shock['start']} to {shock['end']}"
    if k == "order":
        return f"{shock['order']} × {shock['factor']:g}"
    if k == "supplier":
        return f"{names.get(shock['supplier'], shock['supplier'])} stops supplying"
    return k


def validate(graph: Graph, shocks: list[dict]) -> list[dict]:
    if not shocks:
        raise SandboxError("Add at least one change to try")
    if len(shocks) > 6:
        raise SandboxError("Try at most six changes at a time")
    names = _names(graph)
    orders = {r["id"] for r in rows(graph, "MATCH (o:Order) RETURN o.id AS id")}
    out = []
    for s in shocks:
        k = s.get("kind")
        if k == "part":
            if s.get("item") not in names:
                raise SandboxError(f"Unknown part {s.get('item')}")
            if not (s.get("eol") or s.get("price") or s.get("lead_weeks")):
                raise SandboxError(f"Say what changes for {s['item']}: price, lead time or end of life")
            s = {"kind": k, "item": s["item"], "price": float(s["price"]) if s.get("price") else None,
                 "lead_weeks": int(s["lead_weeks"]) if s.get("lead_weeks") else None, "eol": bool(s.get("eol"))}
        elif k == "person":
            if not str(s.get("person", "")).startswith("P-") or s["person"] not in names:
                raise SandboxError(f"Unknown person {s.get('person')}")
            start = date.fromisoformat(s["start"]).isoformat()
            end = date.fromisoformat(s["end"]).isoformat() if s.get("end") else None
            if end and end < start:
                raise SandboxError("The absence ends before it starts")
            s = {"kind": k, "person": s["person"], "start": start, "end": end}
        elif k == "order":
            if s.get("order") not in orders:
                raise SandboxError(f"Unknown order {s.get('order')}")
            factor = float(s.get("factor") or 1)
            if not 0 < factor <= 10:
                raise SandboxError("Scale an order by more than 0 and at most 10")
            s = {"kind": k, "order": s["order"], "factor": factor}
        elif k == "supplier":
            if not str(s.get("supplier", "")).startswith("S-") or s["supplier"] not in names:
                raise SandboxError(f"Unknown supplier {s.get('supplier')}")
            s = {"kind": k, "supplier": s["supplier"]}
        else:
            raise SandboxError(f"Unknown kind of change {k!r}")
        out.append(s | {"label": describe(s, names)})
    return out


def _apply(fork: Graph, shocks: list[dict]) -> None:
    for s in shocks:
        if s["kind"] == "part" and s["eol"]:
            fork.query("MATCH (i:Item {id:$id}) SET i.lifecycle = 'end of life'", {"id": s["item"]})
        elif s["kind"] == "person":
            fork.query("""MATCH (p:Person {id:$id})
                          CREATE (p)-[:HAS_ABSENCE]->(:Absence {id: $id + ':sandbox:' + $start, start_date:$start,
                                                                end_date:$end, kind:$kind})""",
                       {"id": s["person"], "start": s["start"], "end": s["end"] or "2099-12-31",
                        "kind": "leaves the company" if not s["end"] else "away"})
        elif s["kind"] == "order":
            fork.query("""MATCH (o:Order {id:$id})
                          WITH o, toInteger(round(o.qty * $f)) - o.qty AS delta
                          SET o.qty = o.qty + delta
                          WITH o, delta OPTIONAL MATCH (o)-[:FULFILLED_BY]->(b:Build) SET b.qty = b.qty + delta""",
                       {"id": s["order"], "f": s["factor"]})
        elif s["kind"] == "supplier":
            fork.query("MATCH (:Supplier {id:$id})-[:QUOTED]->(q:Quote) DETACH DELETE q", {"id": s["supplier"]})


def _assess(fork: Graph, shocks: list[dict], today: date) -> dict:
    """What breaks on this copy. Findings have stable keys so runs can be compared."""
    findings: dict[str, dict] = {}
    names = _names(fork)
    by_name = {v: k for k, v in names.items()}
    orders = {o["id"]: o for o in rows(fork, ORDERS, {})}
    horizon = max([r["d"] for r in rows(fork, "MATCH (b:Build) RETURN b.planned_date AS d") if r["d"]]
                  + [(today + timedelta(weeks=16)).isoformat()])
    away = {}
    for a in rows(fork, AWAY, {"from": today.isoformat(), "to": horizon}):
        away.setdefault(a["id"], a)
    notes = supply.notices(fork)
    builds_at_risk, exposed, cost, tasks = set(), set(), Decimal(0), 0

    def add(key, severity, title, detail, nodes, kind):
        findings.setdefault(key, {"key": key, "severity": severity, "title": title, "detail": detail,
                                  "nodes": [n for n in nodes if n], "kind": kind})

    def when(a):
        return f"leaves Flyvi from {a['start']}" if a["end"] >= "2099" else f"is away {a['start']} to {a['end']}"

    def expose(order_id, because):
        o = orders.get(order_id)
        if not o:
            return
        exposed.add(order_id)
        add(f"order:{order_id}", "high", f"{order_id} for {o['customer']} is exposed",
            f"{o['qty']} units due {o['due']}. {because}", [order_id], "order")
        if o["owner_id"] in away:
            a = away[o["owner_id"]]
            add(f"account_owner_away:{order_id}", "high", f"{o['customer']}'s account owner is unavailable",
                f"{order_id} is exposed and {o['owner']} {when(a)}. Backup: {a['backup'] or 'none recorded'}.",
                [order_id, o["owner_id"]], "people")

    for s in [s for s in shocks if s["kind"] == "part"]:
        lead = s["lead_weeks"]
        if s["eol"]:
            lead = NO_SUPPLY_WEEKS
        if lead is None:
            known = supply.lead_time(fork, s["item"], today, notes.get(s["item"]))["weeks"]
            lead = known if known is not None else NO_SUPPLY_WEEKS
        price = Decimal(str(s["price"])) if s["price"] else None
        r = analyse(fork, ChangeEvent(s["item"], price, "INR", None, lead, today))
        if r["status"] != "ok":
            continue
        for b in r["builds"]:
            if not b["at_risk"]:
                continue
            builds_at_risk.add(b["build"])
            add(f"build:{b['build']}", "high", f"{b['build']} is short of {s['item']}",
                f"{b['revision']} build on {b['planned_date']} needs {b['parts_needed']}; {b['shortfall']} cannot "
                f"arrive in time.", [b["build"], b["revision"], s["item"]], "build")
            for o in b["orders"]:
                expose(o["order"], f"Its build {b['build']} is short of {s['item']}.")
            planner = by_name.get(b["planner"] or "")
            if planner in away and away[planner]["start"] <= b["planned_date"] <= away[planner]["end"]:
                a = away[planner]
                add(f"planner_away:{b['build']}", "high", f"{b['build']} needs replanning while its planner is away",
                    f"{b['planner']} {when(a)}. Backup: {a['backup'] or 'none recorded'}.", [b["build"], planner], "people")
        if r["cost"]:
            cost += Decimal(str(r["cost"]["total_delta"]))
        if s["eol"] or lead >= NO_SUPPLY_WEEKS:
            usable = [a for a in r["alternates"] if a["status"] != "rejected" and a["quotes"]]
            add(f"no_fallback:{s['item']}", "high" if not usable else "medium",
                f"No qualified replacement for {s['item']}" if not usable else f"{s['item']} needs a qualified replacement",
                "Every alternate on record is rejected, unqualified or unquoted." if not usable else
                f"{', '.join(a['id'] for a in usable)} {'is' if len(usable) == 1 else 'are'} quoted but not qualified: "
                f"engineering review and requalification come first.",
                [s["item"]] + [a["id"] for a in r["alternates"]], "part")
        for a in r["actions"]:
            tasks += 1
            pid = by_name.get(a["owner"] or "")
            if pid in away:
                w = away[pid]
                add(f"owner_away:{a['kind']}:{a['target']}", "high", f"{a['title']}: its owner is unavailable",
                    f"{a['owner']} {when(w)}. Backup: {w['backup'] or 'none recorded'}. "
                    f"Required by the change policy: {a['why']}.", [a["target"], pid], "people")

    for s in [s for s in shocks if s["kind"] == "order"]:
        for b in rows(fork, BUILDS_OF_ORDER, {"id": s["order"]}):
            base = round(b["qty"] / s["factor"]) if s["factor"] else b["qty"]
            delta = b["qty"] - base
            if delta <= 0:
                continue
            for p in supply.explode(fork, b["revision"]):
                extra = int(p["per_unit"]) * delta
                on_shelf = max(p["on_hand"] - p["allocated"], 0) if p["on_hand"] >= 0 else 0
                free = max(on_shelf - (supply.planned_need(fork, p["id"]) - extra), 0)  # after the builds already planned
                if extra <= free:
                    continue
                lead = supply.lead_time(fork, p["id"], today, notes.get(p["id"]))
                ready = supply.weeks(today, lead["weeks"] + BUILD_WEEKS).isoformat() if lead["weeks"] is not None else None
                if ready and ready <= b["planned_date"]:
                    continue
                builds_at_risk.add(b["build"])
                add(f"short:{p['id']}:{b['build']}", "high", f"{b['build']} cannot get {extra - free} more {p['id']}",
                    f"The larger order needs {extra} more; {free} are free. "
                    + (f"New supply takes {lead['weeks']} weeks ({lead['basis']}), ready about {ready}, after "
                       f"the build on {b['planned_date']}." if ready else "No lead time is on record."),
                    [b["build"], p["id"], s["order"]], "build")
                expose(s["order"], f"The larger quantity cannot be built on {b['planned_date']}.")

    for s in [s for s in shocks if s["kind"] == "person"]:
        a = scenarios.absence_impact(fork, s["person"], s["start"], s["end"] or "2099-12-31")
        who = names.get(s["person"], s["person"])
        for c in a.get("conflicts", []):
            add(f"conflict:{s['person']}:{c}", "medium", c, f"Hand it over before {s['start']} (HB-HR-02).",
                [s["person"]], "people")
        leaving = not s["end"]
        from neura1 import rescue
        captured = rescue.coverage(fork, s["person"])
        for k in [k for k in a.get("knowledge_at_risk", []) if k["share"] >= (0.3 if leaving else 0.5)][:4]:
            n = captured.get(k["id"], 0)
            add(f"knowledge:{k['id']}", "low" if n else ("high" if k["share"] >= 0.7 or leaving else "medium"),
                f"Knowledge of {k['id']} leaves with {who}" if not n else f"Knowledge of {k['id']}: captured from {who}",
                f"Flyvi relies on {who} more than anyone for {k['id']} ({round(100 * k['share'])}% of the evidence: "
                f"{', '.join(k['why'][:3])}). Next best: {k['next_best'] or 'nobody'}."
                + (f" {n} answer{'s' if n > 1 else ''} already captured in Knowledge rescue." if n else ""),
                [k["id"], s["person"]], "knowledge")
        if leaving:
            for o in a.get("owned", []):
                add(f"owner_gone:{o['id']}", "high", f"{o['id']} needs a new owner",
                    f"{who} owns {o['name']}. Every change, review and question about it has gone to them.",
                    [o["id"], s["person"]], "people")
            made = [d for d in a.get("decisions", [])]
            if made:
                add(f"decisions:{s['person']}", "medium", f"{who}'s reasoning behind {len(made)} recorded decision"
                    f"{'s' if len(made) > 1 else ''}",
                    "; ".join(f"{d['id']}: {d['summary']}" for d in made[:3]) + ". Capture the reasoning before they go.",
                    [s["person"]] + [d["id"] for d in made], "knowledge")
        for pr in a.get("led_projects", []):
            add(f"lead:{pr['id']}", "medium", f"{pr['name']} needs an interim lead",
                f"{who} leads it" + (f"; target {pr['target_date']}." if pr.get("target_date") else "."),
                [pr["id"], s["person"]], "people")
        for o in orders.values():  # customers this person looks after, with orders due while they are away
            if o["owner_id"] == s["person"] and s["start"] <= (o["due"] or "") <= (s["end"] or "2099-12-31"):
                add(f"account_owner_away:{o['id']}", "medium", f"{o['customer']}'s account owner is unavailable",
                    f"{o['id']} is due {o['due']}, while {who} {when(away.get(s['person'], {'start': s['start'], 'end': s['end'] or '2099'}))}.",
                    [o["id"], s["person"]], "people")

    for s in [s for s in shocks if s["kind"] == "supplier"]:
        still = {r["id"] for r in rows(fork, QUOTED_PARTS, {"today": today.isoformat()})}
        used = {p["id"] for r in rows(fork, "MATCH (r:Revision {status:'released'}) RETURN r.id AS id")
                for p in supply.explode(fork, r["id"])}
        lost = sorted(i for i in s.get("_quoted_before", []) if i not in still and i in used)
        for item in lost:
            add(f"no_quote:{item}", "high", f"Nobody is quoting {item} any more",
                f"{names.get(s['supplier'])} was the only supplier quoting it.", [item, s["supplier"]], "part")

    value = sum(orders[o]["value"] for o in exposed if o in orders)
    penalty = sum(round(orders[o]["value"] * orders[o]["penalty_cap"] / 100) for o in exposed if o in orders)
    people = {n for f in findings.values() for n in f["nodes"] if str(n).startswith("P-")}
    metrics = {"builds_at_risk": len(builds_at_risk), "orders_exposed": len(exposed), "value_at_risk": int(value),
               "max_penalty": int(penalty), "cost_increase": int(cost), "tasks": tasks,
               "people_stretched": len(people),
               "knowledge_gaps": sum(1 for f in findings.values() if f["kind"] == "knowledge" and f["severity"] != "low")}
    return {"findings": list(findings.values()), "metrics": metrics}


def _on_copy(graph: Graph, shocks: list[dict], today: date) -> dict:
    name = f"sandbox_{uuid.uuid4().hex[:10]}"
    t0 = time.perf_counter()
    graph.copy(name)
    fork = get_graph(name)
    copied = time.perf_counter()
    try:
        _apply(fork, shocks)
        out = _assess(fork, shocks, today)
    finally:
        fork.delete()
    return out | {"copy_ms": round((copied - t0) * 1000, 1), "total_ms": round((time.perf_counter() - t0) * 1000, 1)}


def run(graph: Graph, shocks: list[dict], today: date | None = None) -> dict:
    today = today or date.today()
    shocks = validate(graph, shocks)
    quoted = sorted(r["id"] for r in rows(graph, QUOTED_PARTS, {"today": today.isoformat()}))
    for s in shocks:
        if s["kind"] == "supplier":
            s["_quoted_before"] = quoted
    t0 = time.perf_counter()
    combined = _on_copy(graph, shocks, today)
    singles = [_on_copy(graph, [s], today) for s in shocks] if len(shocks) > 1 else [combined]
    alone = {f["key"] for r in singles for f in r["findings"]}
    order = {"high": 0, "medium": 1, "low": 2}
    findings = sorted(combined["findings"], key=lambda f: (f["key"] in alone, order.get(f["severity"], 3), f["key"]))
    for f in findings:
        f["only_in_combination"] = len(shocks) > 1 and f["key"] not in alone
    for s in shocks:
        s.pop("_quoted_before", None)
    return {
        "status": "ok", "today": today.isoformat(), "shocks": shocks,
        "metrics": combined["metrics"],
        "each_alone": [{"label": s["label"], "metrics": r["metrics"], "findings": len(r["findings"])}
                       for s, r in zip(shocks, singles)],
        "findings": findings,
        "only_in_combination": sum(1 for f in findings if f["only_in_combination"]),
        "touched": sorted({n for f in findings for n in f["nodes"]}),
        "copies": len(singles) + (1 if len(shocks) > 1 else 0),
        "copy_ms": combined["copy_ms"], "total_ms": round((time.perf_counter() - t0) * 1000, 1),
        "assumptions": ["Each scenario runs on a copy of the company graph; the real graph is never written",
                        f"End of life, or no supplier left quoting a part, means no new supply within {NO_SUPPLY_WEEKS // 52} years",
                        f"{BUILD_WEEKS} weeks from parts arriving to a finished unit",
                        "A larger order grows the build that fulfils it, on the same date"],
    }
