"""Inventory: what Flyvi holds, what it paid, where it came from, and where it is going.

Stores and purchasing records live in the same graph as everything else: purchase orders, goods received, and a stock
ledger in which every movement (opening balance, receipt, issue to a build, adjustment) is one row. Because they sit
next to the bill of materials, builds, supplier notices, decisions and people, one part can be answered completely:
how many, where, what it cost over time, when it was last ordered and from whom, how reliable that supplier has been,
what the planned builds need, and what the company already decided about it. Everything here is computed by code.
"""

from datetime import date, timedelta
from decimal import Decimal

from falkordb import Graph

from neura1 import supply
from neura1.graph import rows

ITEMS = """
MATCH (i:Item {kind:'part'})
OPTIONAL MATCH (po:PurchaseOrder)-[:ORDERS]->(i)
OPTIONAL MATCH (po)-[:FROM_SUPPLIER]->(s:Supplier)
WITH i, po, s ORDER BY po.ordered_on DESC
WITH i, collect({id: po.id, ordered_on: po.ordered_on, expected_on: po.expected_on, status: po.status, qty: po.qty,
                 unit_price: po.unit_price, supplier: s.name}) AS pos
RETURN i.id AS id, i.name AS name, i.mpn AS mpn, i.manufacturer AS manufacturer, i.category AS category,
       i.uom AS uom, i.hsn AS hsn, i.location AS location, i.reorder_level AS reorder_level,
       i.on_hand AS on_hand, i.allocated AS allocated, i.lifecycle AS lifecycle, pos
ORDER BY category, id
"""

LEDGER = """
MATCH (m:StockMove)-[:MOVES]->(:Item {id:$id})
RETURN m.id AS id, m.date AS date, m.qty AS qty, m.kind AS kind, m.ref AS ref, m.location AS location, m.note AS note
ORDER BY date, id
"""

ORDERS = """
MATCH (po:PurchaseOrder)-[:ORDERS]->(:Item {id:$id})
OPTIONAL MATCH (po)-[:FROM_SUPPLIER]->(s:Supplier)
OPTIONAL MATCH (po)-[:PRICED_BY]->(q:Quote)
OPTIONAL MATCH (g:Receipt)-[:AGAINST]->(po)
RETURN po.id AS id, po.qty AS qty, po.unit_price AS unit_price, po.currency AS currency, po.ordered_on AS ordered_on,
       po.expected_on AS expected_on, po.status AS status, s.id AS supplier_id, s.name AS supplier, q.id AS quote,
       collect(CASE WHEN g IS NULL THEN NULL ELSE {id: g.id, qty: g.qty, received_on: g.received_on, lot: g.lot,
               rejected: g.rejected, note: g.note, location: g.location} END) AS receipts
ORDER BY ordered_on DESC
"""

QUOTES = """
MATCH (s:Supplier)-[:QUOTED]->(q:Quote)-[:FOR]->(:Item {id:$id})
RETURN q.id AS id, s.name AS supplier, q.unit_price AS unit_price, q.moq AS moq, q.lead_weeks AS lead_weeks,
       q.valid_from AS valid_from, q.valid_until AS valid_until
ORDER BY valid_from
"""

CONTEXT = """
MATCH (i:Item {id:$id})
OPTIONAL MATCH (o:Person)-[:OWNS]->(i)
OPTIONAL MATCH (d:Decision)-[:ABOUT]->(i) WHERE coalesce(d.status, 'active') = 'active'
OPTIONAL MATCH (a:Action)-[:CONCERNS]->(i) WHERE coalesce(a.status, 'open') <> 'done'
OPTIONAL MATCH (dep:Item)-[:DEPENDS_ON]->(i)
RETURN o.id AS owner_id, o.name AS owner,
       collect(DISTINCT {id: d.id, outcome: d.outcome, summary: d.summary, decided_at: d.decided_at}) AS decisions,
       collect(DISTINCT {id: a.id, title: a.title, status: a.status}) AS tasks,
       collect(DISTINCT {id: dep.id, name: dep.name, kind: dep.kind}) AS dependents
"""

WHERE_USED = """
MATCH (prod:Item {kind:'product'})-[:HAS_REV]->(top:Revision)
MATCH p = (top)-[:CONTAINS*1..8]->(:Item {id:$id})
WITH top, prod, reduce(q = 1, r IN relationships(p) | q * r.qty) AS qty
RETURN top.id AS revision, prod.name AS product, top.status AS status, sum(qty) AS per_unit
ORDER BY revision
"""

DEMAND = supply.DEMAND


HORIZON_DAYS = 182  # how far ahead stock is projected


def usage(ledger: list[dict], today: date, days: int = 365) -> int:
    """Units issued to builds over the last `days` (adjustments and scrap are not usage)."""
    since = (today - timedelta(days=days)).isoformat()
    return -sum(m["qty"] for m in ledger if m["kind"] == "issue" and m["date"] >= since and (m["qty"] or 0) < 0)


def forecast(free: int, reorder: int, demand: list[dict], orders: list[dict], ledger: list[dict],
             lead_weeks: int | None, today: date) -> dict:
    """Project free stock forward: planned builds take their parts on their dates, open orders arrive on their
    expected dates, and after the last planned build the part keeps being used at last year's rate.
    Returns when it first runs short, when it drops below the reorder level, and the last day to order."""
    events: dict[str, int] = {}
    for d in demand:
        if d["planned_date"] and d["planned_date"] >= today.isoformat():
            events[d["planned_date"]] = events.get(d["planned_date"], 0) - int(d["need"] or 0)
    for o in orders:
        if o["status"] in ("open", "partially_received") and o.get("expected_on"):
            left = int(o["qty"] or 0) - int(o.get("received_qty") or 0)
            day = max(o["expected_on"], today.isoformat())
            events[day] = events.get(day, 0) + left
    last_build = max((d["planned_date"] for d in demand if d["planned_date"]), default=today.isoformat())
    daily = usage(ledger, today) / 365
    level, points, first_short, below = float(free), [], None, None
    for i in range(HORIZON_DAYS + 1):
        day = today + timedelta(days=i)
        iso = day.isoformat()
        before = level
        level += events.get(iso, 0)
        if iso > last_build:
            level -= daily
        if level < 0 and first_short is None:
            first_short = {"date": iso, "short": int(round(-level)) if before >= 0 else int(round(-level)),
                           "build": next((d["build"] for d in demand if d["planned_date"] == iso), None)}
        if reorder and level < reorder and below is None:
            below = iso
        if i % 7 == 0 or iso in events:
            points.append({"date": iso, "level": round(level)})
    trigger = first_short["date"] if first_short else below
    order_by = None
    if trigger and lead_weeks is not None:
        order_by = (date.fromisoformat(trigger) - timedelta(weeks=lead_weeks)).isoformat()
    return {"points": points, "runs_short": first_short, "below_reorder_on": below, "order_by": order_by,
            "late": bool(order_by and order_by < today.isoformat()), "lead_weeks": lead_weeks,
            "monthly_usage": round(daily * 30.4), "horizon_days": HORIZON_DAYS}


def _num(v) -> Decimal | None:
    try:
        return Decimal(str(v)) if v not in (None, "") else None
    except Exception:
        return None


def _stock(on_hand, allocated, reorder, planned: int, on_order: int) -> dict:
    """Stock as a buyer reads it: what is left after the planned builds take their share, plus what is on order,
    against the reorder level. Allocated stock is reserved for other demand."""
    if on_hand is None:
        return {"on_hand": None, "allocated": None, "free": None, "available": None, "status": "no_record"}
    free = max(on_hand - (allocated or 0), 0)
    available = max(free - planned, 0)
    status = "short" if planned > free + on_order else \
        "below_reorder" if reorder and available + on_order < reorder else "ok"
    return {"on_hand": on_hand, "allocated": allocated or 0, "free": free, "available": available, "status": status}


def items(graph: Graph, today: date | None = None, with_forecast: bool = True) -> list[dict]:
    """Every part: stock against its reorder level, the last order, and what is on order now."""
    today = today or date.today()
    out = []
    for r in rows(graph, ITEMS):
        pos = [p for p in r.pop("pos") if p.get("id")]
        last = next((p for p in pos if p["status"] != "cancelled"), None)
        open_pos = [p for p in pos if p["status"] in ("open", "partially_received")]
        price = _num(last["unit_price"]) if last else None
        on_order = sum(p["qty"] or 0 for p in open_pos)
        planned = supply.planned_need(graph, r["id"])
        stock = _stock(r["on_hand"], r["allocated"], r["reorder_level"], planned, on_order)
        out.append(r | stock | {
            "planned_need": planned, "last_order": last, "on_order": on_order,
            "next_delivery": min((p["expected_on"] for p in open_pos if p["expected_on"]), default=None),
            "last_price": float(price) if price is not None else None,
            "stock_value": float(price * r["on_hand"]) if price is not None and r["on_hand"] else None,
            "orders": len(pos),
        })
    if with_forecast:
        notes = supply.notices(graph)
        for r in out:
            if r["free"] is None:
                r["forecast"] = None
                continue
            ledger = rows(graph, LEDGER, {"id": r["id"]})
            demand = [d | {"need": int(d["need"] or 0)} for d in rows(graph, DEMAND, {"id": r["id"]})]
            orders = [o | {"received_qty": sum((g or {}).get("qty") or 0 for g in o["receipts"])}
                      for o in rows(graph, ORDERS, {"id": r["id"]})]
            lead = supply.lead_time(graph, r["id"], today, notes.get(r["id"]))
            f = forecast(r["free"], r["reorder_level"] or 0, demand, orders, ledger, lead["weeks"], today)
            r["forecast"] = {k: f[k] for k in ("runs_short", "below_reorder_on", "order_by", "late", "lead_weeks",
                                               "monthly_usage")}
            r["outlook"] = outlook(r["id"], f, today) if (f["runs_short"] or f["below_reorder_on"]) else None
    return out



def item(graph: Graph, item_id: str, today: date | None = None) -> dict:
    """Everything about one part."""
    today = today or date.today()
    found = [r for r in items(graph, today, with_forecast=False) if r["id"].upper() == item_id.upper()
             or (r["mpn"] or "").upper() == item_id.upper()]
    if not found:
        return {"status": "unknown_item", "item": item_id}
    base = found[0]
    pid = base["id"]

    ledger, balance = [], 0
    for m in rows(graph, LEDGER, {"id": pid}):
        balance += m["qty"] or 0
        ledger.append(m | {"balance": balance})
    orders = rows(graph, ORDERS, {"id": pid})
    for o in orders:
        o["receipts"] = [g for g in o["receipts"] if g]
        got = sorted(o["receipts"], key=lambda g: g["received_on"] or "")
        o["received_on"] = got[-1]["received_on"] if got else None
        o["received_qty"] = sum((g["qty"] or 0) - (g["rejected"] or 0) for g in got)
        o["rejected_qty"] = sum(g["rejected"] or 0 for g in got)
        o["lead_days"] = (date.fromisoformat(o["received_on"]) - date.fromisoformat(o["ordered_on"])).days \
            if o["received_on"] and o["ordered_on"] else None
        o["on_time"] = (o["received_on"] <= o["expected_on"]) if o["received_on"] and o["expected_on"] else None
    quotes = rows(graph, QUOTES, {"id": pid})
    notice = supply.notices(graph).get(pid)

    prices = [{"date": o["ordered_on"], "price": float(_num(o["unit_price"])), "kind": "paid", "ref": o["id"],
               "supplier": o["supplier"], "qty": o["qty"]} for o in orders if _num(o["unit_price"]) is not None]
    prices += [{"date": q["valid_from"], "until": q["valid_until"], "price": float(_num(q["unit_price"])), "kind": "quoted",
                "ref": q["id"], "supplier": q["supplier"]} for q in quotes if _num(q["unit_price"]) is not None]
    if notice and notice.get("new_unit_price"):
        prices.append({"date": notice.get("effective_date") or notice["received"], "price": float(notice["new_unit_price"]),
                       "kind": "notice", "ref": notice["source"], "supplier": None})
    prices.sort(key=lambda p: p["date"] or "")

    suppliers: dict[str, dict] = {}
    for o in orders:
        s = suppliers.setdefault(o["supplier"] or "unknown", {"name": o["supplier"], "orders": 0, "qty": 0,
                                                              "lead_days": [], "on_time": 0, "delivered": 0,
                                                              "rejected": 0, "last_price": None, "last_ordered": None})
        s["orders"] += 1
        s["qty"] += o["qty"] or 0
        s["rejected"] += o["rejected_qty"]
        if o["lead_days"] is not None:
            s["lead_days"].append(o["lead_days"])
            s["delivered"] += 1
            s["on_time"] += 1 if o["on_time"] else 0
        if not s["last_ordered"] or (o["ordered_on"] or "") > s["last_ordered"]:
            s["last_ordered"], s["last_price"] = o["ordered_on"], o["unit_price"]
    for s in suppliers.values():
        days = s.pop("lead_days")
        s["avg_lead_days"] = round(sum(days) / len(days)) if days else None

    demand = [d | {"need": int(d["need"] or 0), "per_unit": int(d["per_unit"] or 0)} for d in rows(graph, DEMAND, {"id": pid})]
    need = sum(d["need"] for d in demand)
    lead = supply.lead_time(graph, pid, today, notice)
    projection = forecast(base["free"], base["reorder_level"] or 0, demand, orders, ledger, lead["weeks"], today) \
        if base["free"] is not None else None
    ctx = (rows(graph, CONTEXT, {"id": pid}) or [{}])[0]
    alts = supply.alternates(graph, pid, today)
    last = next((o for o in orders if o["status"] != "cancelled"), None)
    received = next((o for o in orders if o["received_on"]), None)

    return {
        "status": "ok", "today": today.isoformat(),
        "item": {k: base[k] for k in ("id", "name", "mpn", "manufacturer", "category", "uom", "hsn", "location",
                                      "reorder_level", "lifecycle")},
        "stock": {k: base[k] for k in ("on_hand", "allocated", "free", "available", "status")} | {
            "on_order": base["on_order"], "next_delivery": base["next_delivery"],
            "stock_value": base["stock_value"], "last_price": base["last_price"]},
        "last_order": last, "last_received": received, "orders": orders, "quotes": quotes, "notice": notice,
        "price_history": prices, "suppliers": list(suppliers.values()), "ledger": ledger,
        "where_used": rows(graph, WHERE_USED, {"id": pid}), "demand": demand, "planned_need": need,
        "owner": {"id": ctx.get("owner_id"), "name": ctx.get("owner")} if ctx.get("owner_id") else None,
        "decisions": [d for d in ctx.get("decisions", []) if d.get("id")],
        "tasks": [t for t in ctx.get("tasks", []) if t.get("id")],
        "dependents": [d for d in ctx.get("dependents", []) if d.get("id")],
        "alternates": alts, "forecast": projection, "lead": {k: lead.get(k) for k in ("weeks", "basis", "source")},
        "insights": insights(base, orders, prices, notice, demand, need, alts, ledger, today, projection),
    }


def outlook(item_id: str, p: dict, today: date) -> str:
    """One sentence: when the part runs short or low, and when to order by."""
    short = p["runs_short"]
    what = (f"{item_id} runs short on {short['date']}" + (f" ({short['build']} is {short['short']} short)" if short.get("build") else "")
            if short else f"{item_id} drops below its reorder level around {p['below_reorder_on']}")
    if p["order_by"] is None:
        return f"{what}; no lead time is on record, so ask for a quote now."
    if p["late"]:
        return f"{what}. At {p['lead_weeks']} weeks to deliver, it should have been ordered by {p['order_by']}: order now."
    return f"{what}. At {p['lead_weeks']} weeks to deliver, order by {p['order_by']}."


def _rupees(v) -> str:
    v = float(v)
    return f"₹{v:,.2f}".rstrip("0").rstrip(".") if v % 1 else f"₹{v:,.0f}"


def insights(base, orders, prices, notice, demand, need, alts, ledger, today, projection=None) -> list[str]:
    """Plain sentences a buyer would want first, each computed from the records."""
    out = []
    if projection and (projection["runs_short"] or projection["below_reorder_on"]):
        out.append(outlook(base["id"], projection, today))
    free, reorder = base["free"], base["reorder_level"]
    if base["status"] == "no_record":
        out.append("No stock is on record for this part.")
    elif base["status"] == "below_reorder":
        out.append(f"After the planned builds, {base['available']} remain"
                   + (f" with {base['on_order']} on order" if base["on_order"] else "")
                   + f": below the reorder level of {reorder}. Time to order.")
    if need and free is not None:
        held = f" ({base['allocated']} more are allocated to other demand)" if base["allocated"] else ""
        if free >= need:
            out.append(f"The planned builds need {need}; {free} are free{held}, leaving {free - need} after them.")
        else:
            out.append(f"The planned builds need {need}; only {free} are free{held}, so {need - free} must be bought.")
    paid = [p for p in prices if p["kind"] == "paid"]
    if len(paid) >= 2:
        first, last = paid[0], paid[-1]
        change = (last["price"] - first["price"]) / first["price"] * 100 if first["price"] else 0
        out.append(f"Price paid moved from {_rupees(first['price'])} ({first['date'][:7]}) to {_rupees(last['price'])} "
                   f"({last['date'][:7]}), {change:+.0f}% over {len(paid)} orders.")
    if notice and notice.get("new_unit_price"):
        out.append(f"A supplier notice ({notice['received']}) sets {_rupees(notice['new_unit_price'])} from "
                   f"{notice.get('effective_date') or 'its effective date'}"
                   + (f" and a {notice['lead_weeks']}-week lead time" if notice.get("lead_weeks") else "")
                   + (f"; last-time-buy closes {notice['last_time_buy']}." if notice.get("last_time_buy") else "."))
    open_pos = [o for o in orders if o["status"] in ("open", "partially_received")]
    if open_pos:
        o = open_pos[0]
        out.append(f"{o['id']} for {o['qty']} is on order from {o['supplier']}, expected {o['expected_on']}.")
    elif orders:
        out.append("No purchase order is open for this part.")
    delivered = [o for o in orders if o["on_time"] is not None]
    if delivered:
        late = [o for o in delivered if not o["on_time"]]
        days = [o["lead_days"] for o in delivered if o["lead_days"] is not None]
        out.append(f"{len(delivered) - len(late)} of {len(delivered)} deliveries arrived on time; "
                   f"orders took {round(sum(days) / len(days))} days on average from order to stores.")
    rejected = sum(o["rejected_qty"] for o in orders)
    if rejected:
        out.append(f"{rejected} units were rejected at incoming inspection.")
    if not orders and ledger and ledger[0]["kind"] == "opening":
        out.append("No purchase is on record since the opening balance was migrated, so there is no price paid.")
    for a in alts:
        if a["status"] == "rejected":
            why = next((d.get("reason") for d in a["decisions"] if d.get("outcome") == "rejected"), None)
            out.append(f"Do not substitute {a['id']}: rejected" + (f" ({why})." if why else "."))
    return out
