"""Purchasing: Neura1 drafts the order, a person approves it, and the stores record it.

`suggest` works out a purchase order by code from what the graph knows: how much the planned builds need, the reorder
level, free stock and what is already on order; the cheapest valid quote and its minimum order quantity; the newest lead
time (a supplier notice beats a quote); whether ordering before a notified price rise saves money; which planned builds
the order can still reach; and parts the company has already rejected. It also drafts the email to the supplier.
Nothing is ordered until someone allowed to see money approves it (`create`). `receive` books a delivery: a goods
receipt, a stock-ledger movement and the new stock on hand, so the ledger keeps adding up.
"""

import math
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from falkordb import Graph

from neura1 import inventory, supply
from neura1.graph import rows

_lock = threading.Lock()  # order and receipt numbers are allocated one at a time

LAST_PAID = """
MATCH (po:PurchaseOrder)-[:ORDERS]->(:Item {id:$id}) MATCH (po)-[:FROM_SUPPLIER]->(s:Supplier)
RETURN s.id AS supplier_id, s.name AS supplier, po.unit_price AS unit_price, po.ordered_on AS ordered_on
ORDER BY ordered_on DESC LIMIT 1
"""

QUOTES = """
MATCH (s:Supplier)-[:QUOTED]->(q:Quote)-[:FOR]->(:Item {id:$id})
WHERE (q.valid_from IS NULL OR q.valid_from <= $today) AND (q.valid_until IS NULL OR q.valid_until >= $today)
RETURN q.id AS id, s.id AS supplier_id, s.name AS supplier, q.unit_price AS unit_price, q.currency AS currency,
       q.moq AS moq, q.lead_weeks AS lead_weeks, q.valid_until AS valid_until
"""


class PurchasingError(ValueError):
    pass


def _money(v) -> str:
    v = Decimal(str(v))
    return f"₹{v:,.2f}".rstrip("0").rstrip(".") if v % 1 else f"₹{v:,.0f}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def suggest(graph: Graph, item_id: str, today: date | None = None, by: str | None = None) -> dict:
    """The purchase order Neura1 would raise for this part today, and why."""
    today = today or date.today()
    inv = inventory.item(graph, item_id, today)
    if inv.get("status") != "ok":
        raise PurchasingError(f"No part called {item_id}")
    part, stock = inv["item"], inv["stock"]
    if stock["on_hand"] is None:
        raise PurchasingError(f"{part['id']} is not stocked, so there is nothing to reorder")
    pid = part["id"]
    reorder = part["reorder_level"] or 0
    planned, free, on_order = inv["planned_need"], stock["free"], stock["on_order"]
    target = planned + reorder - free - on_order
    reasons = [f"Planned builds need {planned}; {free} are free and {on_order} on order; the reorder level is {reorder}."]
    warnings: list[str] = []

    quotes = rows(graph, QUOTES, {"id": pid, "today": today.isoformat()})
    quote = min(quotes, key=lambda q: (Decimal(str(q["unit_price"])), q["lead_weeks"] or 999)) if quotes else None
    notice = inv["notice"]
    if quote:
        supplier = {"id": quote["supplier_id"], "name": quote["supplier"]}
        price, basis = Decimal(str(quote["unit_price"])), f"quote {quote['id']}, valid until {quote['valid_until']}"
        moq = quote["moq"] or 1
    else:
        last = (rows(graph, LAST_PAID, {"id": pid}) or [None])[0]
        if not last:
            return _needs_quote(part, stock, planned, target, reasons, today)
        supplier = {"id": last["supplier_id"], "name": last["supplier"]}
        price, basis, moq = Decimal(str(last["unit_price"])), f"last price paid ({last['ordered_on']}); no current quote", 1
        if target > 0:
            warnings.append(f"No current quote for {pid}: confirm the price with {supplier['name']} before sending.")

    saving = None
    if notice and notice.get("new_unit_price"):
        new = Decimal(str(notice["new_unit_price"]))
        effective = notice.get("effective_date")
        if effective and effective > today.isoformat() and new > price:
            saving = new - price
            reasons.append(f"The supplier notice raises the price to {_money(new)} from {effective}: ordering now holds "
                           f"{_money(price)} ({basis}).")
        elif not effective or effective <= today.isoformat():
            price, basis = new, f"the supplier notice of {notice['received']}"

    lead = supply.lead_time(graph, pid, today, notice)
    weeks = lead["weeks"]
    expected = today + timedelta(weeks=weeks) if weeks is not None else None

    needed = target > 0
    qty = 0
    if needed:
        qty = max(target, moq)
        qty = int(math.ceil(qty / moq) * moq) if moq > 1 else int(qty)
        reasons.append(f"{target} are needed to cover the builds and restore the reorder level"
                       + (f"; rounded up to {qty} for the minimum order of {moq}." if qty != target else "."))
    else:
        reasons.append("Free stock and orders already placed cover the planned builds and the reorder level.")

    # Free stock, then orders already placed (as they arrive), go to the builds in date order. Only builds left short
    # depend on this new order, and only those it cannot reach in time are a problem.
    short = _short_builds(inv, free)
    reach = [d for d in short if expected and d["planned_date"] >= expected.isoformat()]
    miss = [d for d in short if d not in reach]
    if needed and miss and expected:
        warnings.append(f"This order cannot reach {', '.join(d['build'] for d in miss)} (planned "
                        f"{', '.join(d['planned_date'] for d in miss)}): at {weeks} weeks it arrives {expected.isoformat()}. "
                        f"Replan those builds or find stock elsewhere.")
    if lead["basis"] == "notice":
        reasons.append(f"Lead time {weeks} weeks from the supplier notice"
                       + (f" (the quote said {lead['quote_weeks']})." if lead.get("quote_weeks") not in (None, weeks) else "."))
    elif weeks is not None:
        reasons.append(f"Lead time {weeks} weeks ("
                       + ("how long recent orders actually took" if lead["basis"] == "history" else f"quote {lead['source']}")
                       + ").")
    if notice and notice.get("last_time_buy"):
        used = inventory.usage(inv["ledger"], today)
        warnings.append(f"Last-time-buy closes {notice['last_time_buy']}: after that this part cannot be ordered. "
                        + (f"Flyvi used {used} in the last 12 months (about {round(used / 12)} a month); a two-year buy "
                           f"would be about {planned + 2 * used:,} including the planned builds." if used else
                           "Consider buying for the life of the products that use it."))
    for a in inv["alternates"]:
        if a["status"] == "rejected":
            warnings.append(f"Do not order {a['id']} instead: it was rejected before.")

    total = price * qty
    email = _email(part, supplier, qty, price, quote, expected, by) if needed else None
    return {
        "status": "ok", "today": today.isoformat(), "needed": needed, "item": part, "supplier": supplier,
        "quote_id": quote["id"] if quote else None, "unit_price": float(price), "currency": "INR", "price_basis": basis,
        "qty": qty, "target": max(target, 0), "moq": moq, "total": float(total),
        "saving_vs_notice": float(saving * qty) if saving and qty else None,
        "lead_weeks": weeks, "lead_basis": lead["basis"], "expected_on": expected.isoformat() if expected else None,
        "reaches": [d["build"] for d in reach], "misses": [d["build"] for d in miss],
        "stock": stock, "planned_need": planned, "reasons": reasons, "warnings": warnings, "email": email,
    }


def _short_builds(inv: dict, free: int) -> list[dict]:
    pool = free
    arrivals = sorted((o["expected_on"] or "9999", o["qty"] - o["received_qty"]) for o in inv["orders"]
                      if o["status"] in ("open", "partially_received"))
    out = []
    for d in sorted(inv["demand"], key=lambda x: x["planned_date"] or ""):
        pool += sum(q for when, q in arrivals if when <= (d["planned_date"] or ""))
        arrivals = [(w, q) for w, q in arrivals if w > (d["planned_date"] or "")]
        take = min(pool, d["need"])
        pool -= take
        if take < d["need"]:
            out.append(d | {"short": d["need"] - take})
    return out


def _needs_quote(part: dict, stock: dict, planned: int, target: int, reasons: list[str], today: date) -> dict:
    """Neither a quote nor a past order: the next step is a request for quotation, not an order."""
    reasons = reasons + ([f"{target} are needed, but no supplier has quoted {part['id']} and no past order shows who "
                          f"supplies it."] if target > 0 else [])
    return {"status": "needs_quote", "today": today.isoformat(), "needed": target > 0, "item": part, "supplier": None,
            "quote_id": None, "unit_price": None, "currency": "INR", "price_basis": None, "qty": max(target, 0),
            "target": max(target, 0), "moq": None, "total": None, "saving_vs_notice": None, "lead_weeks": None,
            "lead_basis": "unknown", "expected_on": None, "reaches": [], "misses": [], "stock": stock,
            "planned_need": planned, "reasons": reasons,
            "warnings": [f"Ask suppliers to quote {part['id']} (MPN {part.get('mpn') or part['id']}) before ordering."],
            "email": None}


def _email(part: dict, supplier: dict, qty: int, price: Decimal, quote: dict | None, expected: date | None,
           by: str | None) -> dict:
    ref = f" against your quote {quote['id']}" if quote else ""
    lines = [
        f"Dear {supplier['name'].split(' (')[0]} team,",
        "",
        f"Please supply {qty:,} × {part['id']} ({part['name']}{', MPN ' + part['mpn'] if part.get('mpn') else ''})"
        f"{ref}, at {_money(price)} per unit.",
        f"Requested delivery: {expected.isoformat() if expected else 'please confirm your earliest date'}, to Flyvi "
        f"Technologies Pvt. Ltd. stores, Bengaluru.",
        "Please confirm the order, the delivery date and the lot or date codes you will ship.",
        "",
        "Regards,",
        f"{by or 'Flyvi Technologies'}",
        "Flyvi Technologies Pvt. Ltd.",
    ]
    return {"to": supplier["name"], "subject": f"Purchase order: {qty:,} × {part['id']}", "body": "\n".join(lines)}


def _next(graph: Graph, label: str, prefix: str, width: int) -> str:
    ids = [r["id"] for r in rows(graph, f"MATCH (n:{label}) WHERE n.id STARTS WITH $p RETURN n.id AS id", {"p": prefix})]
    nums = [int(i[len(prefix):]) for i in ids if i[len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) + 1) if nums else 1:0{width}d}"


def create(graph: Graph, item_id: str, qty: int | None, by: str, today: date | None = None) -> dict:
    """Raise the order Neura1 suggested (the quantity may be changed). Prices and supplier always come from the
    records, never from the browser."""
    today = today or date.today()
    draft = suggest(graph, item_id, today, by)
    if draft["status"] != "ok":
        raise PurchasingError(f"No quote or past order for {draft['item']['id']}: request a quote first")
    qty = int(qty if qty is not None else draft["qty"])
    if qty <= 0 or qty > 1_000_000:
        raise PurchasingError("Order between 1 and 1,000,000 units")
    with _lock:
        po_id = _next(graph, "PurchaseOrder", f"PO-{today.year}-", 4)
        graph.query("""
            MATCH (s:Supplier {id:$sid}), (i:Item {id:$item})
            CREATE (po:PurchaseOrder {id:$id, qty:$qty, unit_price:$price, currency:'INR', ordered_on:$today,
                                      expected_on:$expected, status:'open', raised_by:$by, raised_at:$at,
                                      source:'neura1', authority:'neura1'})
            CREATE (po)-[:FROM_SUPPLIER]->(s) CREATE (po)-[:ORDERS]->(i)
            WITH po OPTIONAL MATCH (q:Quote {id:$quote})
            FOREACH (_ IN CASE WHEN q IS NULL THEN [] ELSE [1] END | CREATE (po)-[:PRICED_BY]->(q))
        """, {"sid": draft["supplier"]["id"], "item": draft["item"]["id"], "id": po_id, "qty": qty,
              "price": f"{Decimal(str(draft['unit_price'])):f}", "today": today.isoformat(),
              "expected": draft["expected_on"], "by": by, "at": _now(), "quote": draft["quote_id"]})
    _announce(graph, f"{by} raised {po_id}: {qty:,} × {draft['item']['id']} from {draft['supplier']['name']}, "
                     f"expected {draft['expected_on'] or 'to be confirmed'}.", draft["item"]["id"])
    return {"id": po_id, "qty": qty, "item": draft["item"]["id"], "supplier": draft["supplier"]["name"],
            "unit_price": draft["unit_price"], "total": float(Decimal(str(draft["unit_price"])) * qty),
            "expected_on": draft["expected_on"], "email": _email(draft["item"], draft["supplier"], qty,
                                                                 Decimal(str(draft["unit_price"])),
                                                                 {"id": draft["quote_id"]} if draft["quote_id"] else None,
                                                                 date.fromisoformat(draft["expected_on"]) if draft["expected_on"] else None, by)}


def receive(graph: Graph, po_id: str, qty: int, rejected: int, lot: str | None, by: str,
            today: date | None = None) -> dict:
    """Book a delivery against an open order: goods receipt, stock-ledger movement and stock on hand, together."""
    today = today or date.today()
    found = rows(graph, """
        MATCH (po:PurchaseOrder {id:$id})-[:ORDERS]->(i:Item)
        OPTIONAL MATCH (g:Receipt)-[:AGAINST]->(po)
        RETURN po.status AS status, po.qty AS qty, i.id AS item, i.location AS location,
               coalesce(sum(g.qty), 0) AS received""", {"id": po_id})
    if not found:
        raise PurchasingError(f"No purchase order {po_id}")
    po = found[0]
    if po["status"] not in ("open", "partially_received"):
        raise PurchasingError(f"{po_id} is {po['status']}; only open orders can be received")
    remaining = po["qty"] - int(po["received"])
    if qty <= 0 or qty > remaining:
        raise PurchasingError(f"Receive between 1 and {remaining} units against {po_id}")
    if rejected < 0 or rejected > qty:
        raise PurchasingError("Rejected units must be between 0 and the quantity received")
    accepted = qty - rejected
    with _lock:
        grn = _next(graph, "Receipt", f"GRN-{today.strftime('%y')}-", 4)
        move = _next(graph, "StockMove", "SM-", 4)
        status = "received" if qty == remaining else "partially_received"
        graph.query("""
            MATCH (po:PurchaseOrder {id:$po})-[:ORDERS]->(i:Item)
            CREATE (g:Receipt {id:$grn, qty:$qty, received_on:$today, location:i.location, lot:$lot, rejected:$rej,
                               note:$note, recorded_by:$by, source:'neura1', authority:'neura1'})
            CREATE (g)-[:AGAINST]->(po) CREATE (g)-[:RECEIVES]->(i)
            CREATE (m:StockMove {id:$move, date:$today, qty:$acc, kind:'receipt', ref:$grn, location:i.location,
                                 note:$mnote, source:'neura1', authority:'neura1'})
            CREATE (m)-[:MOVES]->(i)
            SET i.on_hand = coalesce(i.on_hand, 0) + $acc, po.status = $status
        """, {"po": po_id, "grn": grn, "qty": qty, "today": today.isoformat(), "lot": lot or "", "rej": rejected,
              "note": f"{rejected} rejected at incoming inspection" if rejected else "", "by": by, "move": move,
              "acc": accepted, "mnote": f"Received against {po_id}" + (f" ({rejected} rejected)" if rejected else ""),
              "status": status})
    _announce(graph, f"{by} received {accepted:,} × {po['item']} against {po_id}"
                     + (f" ({rejected} rejected at inspection)" if rejected else "") + ".", po["item"])
    return {"receipt": grn, "movement": move, "accepted": accepted, "status": status, "item": po["item"]}


def _announce(graph: Graph, text: str, item: str) -> None:
    """Tell #supply. No prices: the channel is open to everyone."""
    from neura1 import chat
    chat.notify(graph, "supplier_change", text, [{"label": f"Open {item}", "href": f"/inventory?item={item}"}])
