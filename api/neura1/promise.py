"""Can we promise this? A delivery commitment checked across parts, people, knowledge and certifications.

"Can we deliver 50 PDU-28 by 15 December?" is answered from the graph, by code:
  * parts: the bill of materials exploded to parts, free stock, and how long new supply takes by the newest information
    on record (a supplier notice beats a quote);
  * people: who owns the product, its modules, the firmware and tests that depend on its parts, and whether they are
    away before the date (leave details only for viewers allowed to see them);
  * knowledge: work only one person understands, when that person is away;
  * certifications: the revision must be released and its qualifications valid on the date.
The answer is yes, yes with risks, or no with the earliest realistic date and what would change it. It also states
what a stock-and-quote check alone would have said, because that is the answer most companies act on today.
"""

from datetime import date, timedelta
from decimal import Decimal

from falkordb import Graph

from neura1 import brain, supply
from neura1.access import Viewer
from neura1.graph import rows

BUILD_WEEKS = 3  # from the last part arriving to shipping: assembly, test and dispatch (an assumption, shown)

PEOPLE = """
MATCH p = (top:Revision {id:$rev})-[:CONTAINS*0..8]->(x)
WITH DISTINCT x
OPTIONAL MATCH (i:Item)-[:HAS_REV]->(x)
WITH coalesce(i, x) AS thing
MATCH (o:Person)-[:OWNS]->(thing)
RETURN DISTINCT o.id AS id, o.name AS name, thing.id AS owns, labels(thing)[0] AS label
UNION
MATCH (top:Revision {id:$rev})-[:CONTAINS*1..8]->(part:Item)<-[:DEPENDS_ON]-(d:Item)<-[:OWNS]-(o:Person)
RETURN DISTINCT o.id AS id, o.name AS name, d.id AS owns, d.kind AS label
UNION
MATCH (prod:Item)-[:HAS_REV]->(:Revision {id:$rev}), (prod)-[:HAS_REV]->(:Revision)<-[:BUILDS]-(b:Build)<-[:OWNS]-(o:Person)
RETURN DISTINCT o.id AS id, o.name AS name, 'builds of ' + prod.id AS owns, 'Build' AS label
"""

AWAY = """
MATCH (p:Person {id:$id})-[:HAS_ABSENCE]->(a:Absence) WHERE a.end_date >= $from AND a.start_date <= $to
OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p)
RETURN a.start_date AS start, a.end_date AS end, b.name AS backup ORDER BY start LIMIT 1
"""

CERTS = """
MATCH (c:Certification)-[:CERTIFIES]->(:Revision {id:$rev})
RETURN c.id AS id, c.name AS name, c.status AS status, c.valid_until AS valid_until
"""


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def check(graph: Graph, product: str, qty: int, due: date, viewer: Viewer, today: date | None = None,
          build_weeks: int = BUILD_WEEKS) -> dict:
    today = today or date.today()
    if qty <= 0:
        return {"status": "bad_request", "message": "Quantity must be at least 1"}
    found = supply.resolve_revision(graph, product)
    if len(found) != 1:
        return {"status": "unresolved", "candidates": found, "message": f"Which revision of {product}?"}
    rev = found[0]
    constraints: list[dict] = []
    ready_dates: list[tuple[date, str]] = []
    fixes: list[str] = []

    def add(kind, subject, status, detail, **extra):
        constraints.append({"kind": kind, "subject": subject, "status": status, "detail": detail} | extra)

    # Revision and certifications
    if rev["status"] != "released":
        add("revision", rev["id"], "blocker", f"{rev['id']} is {rev['status']}, not released for production.")
        released = [r for r in supply.resolve_revision(graph, rev["item"]) if r["status"] == "released"]
        if released:
            fixes.append(f"Quote {released[0]['id']}, the released revision, instead.")
    for c in rows(graph, CERTS, {"rev": rev["id"]}):
        if c["status"] != "valid" or (c["valid_until"] and c["valid_until"] < due.isoformat()):
            add("certification", c["id"], "blocker", f"{c['name']} is {c['status']} until {c['valid_until']}.")
        else:
            add("certification", c["id"], "ok", f"{c['name']}: valid until {c['valid_until']}.")

    # Parts
    notes = supply.notices(graph)
    erp_dates: list[date] = []
    max_now = None
    for p in supply.explode(graph, rev["id"]):
        need = int(p["per_unit"]) * qty
        recorded = p["on_hand"] >= 0
        on_shelf = max(p["on_hand"] - p["allocated"], 0) if recorded else 0
        planned = supply.planned_need(graph, p["id"])
        free = max(on_shelf - planned, 0)  # the planned builds take free stock first
        per = int(p["per_unit"])
        max_now = (free // per) if max_now is None else min(max_now, free // per)
        short = max(need - free, 0)
        notice = notes.get(p["id"])
        lead = supply.lead_time(graph, p["id"], today, notice)
        base = {"need": need, "free": free, "short": short, "lead": lead, "notice": notice, "planned": planned}
        after = f" after the planned builds take {planned}" if planned else ""
        if not short:
            add("part", p["id"], "ok", f"{need} needed; {free} free in stock{after}.", **base)
            continue
        if lead["quote_weeks"] is not None:  # what a stock-and-quote check would assume
            erp_dates.append(supply.weeks(today, int(lead["quote_weeks"]) + build_weeks))
        if lead["weeks"] is None:
            add("part", p["id"], "unknown",
                f"Short {short} of {need}{after}{'' if recorded else ' (no stock on record)'}, and no lead time is on record.",
                **base)
            fixes.append(f"Get a lead time for {p['id']} ({short} needed) from purchase.")
            continue
        arrive = supply.weeks(today, lead["weeks"])
        ready = arrive + timedelta(weeks=build_weeks)
        ready_dates.append((ready, p["id"]))
        basis = (f"the {notice['received']} supplier notice says {lead['weeks']} weeks"
                 + (f" (the quote said {lead['quote_weeks']})" if lead["quote_weeks"] not in (None, lead["weeks"]) else "")
                 if lead["basis"] == "notice" else
                 f"recent orders took up to {lead['weeks']} weeks ({lead['source']}, no current quote)"
                 if lead["basis"] == "history" else f"quote {lead['source']}: {lead['weeks']} weeks")
        status = "blocker" if ready > due else ("risk" if (due - ready).days < 7 else "ok")
        add("part", p["id"], status, f"Short {short} of {need}{after}; {basis}, so parts arrive {arrive.isoformat()} and "
                                     f"units are ready about {ready.isoformat()}.", **base, ready=ready.isoformat())
        if status == "blocker":
            alts = supply.alternates(graph, p["id"], today)
            for a in alts:
                if a["status"] == "rejected":
                    why = next((d["reason"] for d in a["decisions"] if d.get("outcome") == "rejected"), "")
                    fixes.append(f"Do not switch to {a['id']}: rejected before ({why}).")
                elif a["quote"]:
                    a_ready = supply.weeks(today, int(a["quote"]["lead_weeks"]) + build_weeks)
                    fixes.append(f"{a['id']} is quoted at {a['quote']['lead_weeks']} weeks ({a['quote']['id']}), ready "
                                 f"about {a_ready.isoformat()}, but it is {a['status']}: it needs engineering approval and "
                                 f"requalification first.")
                else:
                    fixes.append(f"{a['id']} is a suggested alternate, {a['status']}, with no quote on record.")
            if notice and notice.get("last_time_buy"):
                fixes.append(f"Place the order for {p['id']} now: last-time-buy closes {notice['last_time_buy']}.")

    # People and knowledge, between today and the due date
    seen = set()
    for o in rows(graph, PEOPLE, {"rev": rev["id"]}):
        if o["id"] in seen:
            continue
        seen.add(o["id"])
        away = rows(graph, AWAY, {"id": o["id"], "from": today.isoformat(), "to": due.isoformat()})
        if not away:
            continue
        if not viewer.sees_leave_of(o["id"]):
            continue  # leave plans are only weighed for viewers allowed to see them
        a = away[0]
        knows = brain.who_knows(graph, o["owns"])
        people = knows["people"]
        total = sum(x["score"] for x in people) or 1
        sole = bool(people) and people[0]["id"] == o["id"] and people[0]["score"] / total > 0.6
        add("people", o["name"], "risk",
            f"{o['name']} owns {o['owns']} and is away {a['start']} to {a['end']}. "
            f"Backup: {a['backup'] or 'none recorded'}."
            + (f" Most of what Flyvi knows about {o['owns']} sits with {o['name']}." if sole else ""),
            owns=o["owns"], sole_knowledge=sole, person_id=o["id"])
        if sole:
            fixes.append(f"Capture what {o['name']} knows about {o['owns']} before {a['start']} (Knowledge rescue).")

    blockers = [c for c in constraints if c["status"] == "blocker"]
    unknown = [c for c in constraints if c["status"] == "unknown"]
    risks = [c for c in constraints if c["status"] == "risk"]
    earliest = max((d for d, _ in ready_dates), default=None)
    limiting = max(ready_dates, default=(None, None))[1]
    if blockers:
        verdict = "no"
        part_block = [c for c in blockers if c["kind"] == "part"]
        headline = (f"No. {limiting} limits the date: the earliest realistic delivery is {earliest.isoformat()}."
                    if part_block and earliest else f"No. {blockers[0]['detail']}")
        if part_block and earliest:
            fixes.insert(0, f"Promise {earliest.isoformat()} instead of {due.isoformat()}.")
        if max_now and part_block:
            fixes.insert(1, f"Ship {min(max_now, qty)} units from free stock now, the rest by "
                            f"{_iso(earliest) or 'a date purchase confirms'}.")
    elif unknown:
        verdict = "unconfirmed"
        headline = f"Not confirmed yet: no lead time on record for {', '.join(c['subject'] for c in unknown)}."
    elif risks:
        verdict = "at_risk"
        headline = f"Yes, with {len(risks)} risk{'s' if len(risks) > 1 else ''} to manage."
    else:
        verdict = "yes"
        headline = f"Yes. Everything needed for {qty} × {rev['id']} by {due.isoformat()} is on record."
    erp_ready = max(erp_dates, default=None)
    erp = ("yes" if not erp_ready or erp_ready <= due else "no")
    cost = None
    if viewer.sees_money:
        extra = Decimal(0)
        for c in constraints:
            q = (c.get("lead") or {}).get("quote")
            if c["kind"] == "part" and c.get("short") and q and q.get("price"):
                price = Decimal(str((c["notice"] or {}).get("new_unit_price") or q["price"]))
                extra += price * max(c["short"], q.get("moq") or 0)
        cost = int(extra) if extra else None
    return {
        "status": "ok", "verdict": verdict, "headline": headline, "product": rev["item"], "revision": rev["id"],
        "qty": qty, "due": due.isoformat(), "today": today.isoformat(), "earliest": _iso(earliest),
        "limiting": limiting, "constraints": constraints, "fixes": list(dict.fromkeys(fixes)),
        "stock_and_quote_says": {"verdict": erp, "ready": _iso(erp_ready),
                                 "note": "Free stock and current quotes only: no supplier notices, people, knowledge "
                                         "or certifications."},
        "purchase_value": cost, "leave_included": viewer.unrestricted or viewer.leader,
        "assumptions": [f"{build_weeks} weeks from the last part arriving to shipping (assembly, test, dispatch)",
                        "Allocated stock is reserved for other demand; planned builds take free stock first",
                        "Without a quote or notice, new supply takes as long as the slowest of the last three orders",
                        "A supplier notice replaces the lead time of an older quote for the same part",
                        "Leave is checked between today and the due date"],
    }
