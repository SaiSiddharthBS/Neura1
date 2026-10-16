"""Company events beyond supplier changes: a person away, a customer escalating, and where the company is fragile.

Like the supplier-change impact, each one is graph traversal plus deterministic rules (HB-HR-02 for handovers,
account escalation rules for customers). No model decides anything here.
"""

from datetime import date

from falkordb import Graph

from neura1 import brain
from neura1 import queries as Q
from neura1.impact import Trace

# ---------- a person away ----------

PERSON_ABSENCES = """
MATCH (p:Person {id:$id})-[:HAS_ABSENCE]->(a:Absence)
RETURN a.start_date AS start_date, a.end_date AS end_date, a.kind AS kind, a.note AS note ORDER BY start_date
"""

PERSON_LINE = """
MATCH (p:Person {id:$id})
OPTIONAL MATCH (p)-[:REPORTS_TO]->(m:Person)
OPTIONAL MATCH (r:Person)-[:REPORTS_TO]->(p)
OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p)
RETURN p.name AS name, p.role AS role, m.id AS manager_id, m.name AS manager,
       collect(DISTINCT r.name) AS reports, b.id AS backup_id, b.name AS backup
"""

# What the person owns, and what is scheduled or due on those things.
OWNED_WORK = """
MATCH (p:Person {id:$id})-[:OWNS]->(x)
OPTIONAL MATCH (a:Action)-[:CONCERNS]->(x) WHERE coalesce(a.status, 'open') <> 'done'
RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.id) AS name,
       x.planned_date AS planned_date, x.valid_until AS valid_until,
       collect(DISTINCT a.title) AS open_tasks_on_it
"""

OPEN_TASKS = """
MATCH (:Person {id:$id})<-[:ASSIGNED_TO]-(a:Action) WHERE coalesce(a.status, 'open') <> 'done'
OPTIONAL MATCH (inv:Investigation)-[:PRODUCED]->(a)
RETURN a.id AS id, a.title AS title, coalesce(a.status, 'open') AS status, inv.id AS investigation
"""

LED_PROJECTS = """
MATCH (:Person {id:$id})-[:LEADS]->(pr:Project) RETURN pr.id AS id, pr.name AS name, pr.target_date AS target_date
"""

# Things this person talks about that nobody else discusses or owns: knowledge that leaves with them.
SOLE_KNOWLEDGE = """
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
"""

DECISIONS_MADE = """
MATCH (:Person {id:$id})<-[:DECIDED_BY]-(d:Decision)-[:ABOUT]->(s:Item)
RETURN d.id AS id, d.outcome AS outcome, s.id AS subject, d.summary AS summary
"""

HANDOVER_POLICY = """
MATCH (ch:Chunk)-[:PART_OF]->(:Source {ref:'HB-HR-02'}) WHERE ch.text CONTAINS '1. '
RETURN ch.id AS chunk LIMIT 1
"""


def _overlaps(day: str | None, start: str, end: str) -> bool:
    return bool(day) and start <= day <= end


def absence_impact(graph: Graph, person_id: str, start: str | None = None, end: str | None = None) -> dict:
    t = Trace(graph)
    line = t.run("person_line", PERSON_LINE, {"id": person_id})
    if not line:
        return {"status": "unknown_person"}
    person = line[0]
    absences = t.run("absences", PERSON_ABSENCES, {"id": person_id})
    if not start and absences:
        start, end = absences[0]["start_date"], absences[0]["end_date"]
    owned = t.run("owned_work", OWNED_WORK, {"id": person_id})
    tasks = t.run("open_tasks", OPEN_TASKS, {"id": person_id})
    led = t.run("led_projects", LED_PROJECTS, {"id": person_id})
    sole = t.run("sole_knowledge", SOLE_KNOWLEDGE, {"id": person_id})
    # Knowledge at risk: subjects where this person is the one the company relies on most.
    subjects = {o["id"] for o in owned} | {x["id"] for x in t.run("person_topics", brain.PERSON_TOPICS, {"id": person_id})}
    at_risk = []
    for sid in sorted(subjects):
        k = brain.who_knows(graph, sid)
        people = k["people"]
        if people and people[0]["id"] == person_id:
            total = sum(p["score"] for p in people) or 1
            nxt = people[1]["name"] if len(people) > 1 else None
            at_risk.append({"id": sid, "share": round(people[0]["score"] / total, 2), "next_best": nxt,
                            "why": sorted({s["signal"] for s in people[0]["signals"]})})
    at_risk.sort(key=lambda a: -a["share"])
    decisions = t.run("decisions_made", DECISIONS_MADE, {"id": person_id})
    policy = (t.run("handover_policy", HANDOVER_POLICY, {}) or [None])[0]
    cite = [policy["chunk"]] if policy else []

    conflicts = []
    if start and end:
        conflicts += [f"{o['id']} is planned for {o['planned_date']}, during the absence"
                      for o in owned if _overlaps(o["planned_date"], start, end)]
        conflicts += [f"Open task '{x['title']}' is assigned to {person['name']}" for x in tasks]

    backup, manager = person["backup"], person["manager"]
    actions = []
    for x in tasks:
        actions.append({"kind": "handover", "target": x["id"], "owner": backup or manager,
                        "title": f"Take over from {person['name']}: {x['title']}",
                        "why": "Open task during planned leave (HB-HR-02 clause 1)", "cites": cite})
    for o in owned:
        actions.append({"kind": "interim_owner", "target": o["id"], "owner": backup or manager,
                        "title": f"Interim owner for {o['id']} while {person['name']} is away",
                        "why": "Owned item needs an interim owner (HB-HR-02 clause 2)", "cites": cite})
    for pr in led:
        actions.append({"kind": "interim_lead", "target": pr["id"], "owner": manager,
                        "title": f"Name an interim lead for {pr['name']}",
                        "why": "Projects led by the person need an interim lead (HB-HR-02 clause 3)", "cites": cite})
    if at_risk or sole or decisions:
        topics = ", ".join(dict.fromkeys([a["id"] for a in at_risk[:4]] + [s["id"] for s in sole[:2]]
                                         + [d["id"] for d in decisions]))
        actions.append({"kind": "handover_note", "target": person_id, "owner": person["name"],
                        "title": f"Write a handover note covering {topics}",
                        "why": "Knowledge only this person holds (HB-HR-02 clause 4)", "cites": cite})
    if manager:
        actions.append({"kind": "confirm_handover", "target": person_id, "owner": manager,
                        "title": f"Confirm {person['name']}'s handover before {start or 'the leave'}",
                        "why": "Manager confirms the handover (HB-HR-02 clause 5)", "cites": cite})

    return {"status": "ok", "person": person | {"id": person_id}, "absence": {"start": start, "end": end},
            "absences": absences, "owned": owned, "open_tasks": tasks, "led_projects": led,
            "sole_knowledge": sole, "knowledge_at_risk": at_risk, "decisions": decisions, "conflicts": conflicts, "actions": actions,
            "trace": t.steps}


# ---------- a customer ----------

CUSTOMER = """
MATCH (c:Customer {id:$id})
OPTIONAL MATCH (am:Person)-[:OWNS]->(c)
OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(am)
RETURN c.id AS id, c.name AS name, am.id AS manager_id, am.name AS account_manager, b.name AS backup
"""

CUSTOMER_ORDERS = """
MATCH (c:Customer {id:$id})-[:PLACED]->(o:Order)
OPTIONAL MATCH (o)-[:FULFILLED_BY]->(b:Build)-[:BUILDS]->(r:Revision)
OPTIONAL MATCH (planner:Person)-[:OWNS]->(b)
OPTIONAL MATCH (a:Action)-[:CONCERNS]->(t) WHERE (t = o OR t = b) AND coalesce(a.status, 'open') <> 'done'
RETURN o.id AS id, o.qty AS qty, o.due_date AS due, o.unit_price AS unit_price,
       o.penalty_pct_per_week AS penalty_pct, o.penalty_cap_pct AS penalty_cap, o.penalty_note AS penalty_note,
       b.id AS build, b.planned_date AS build_date, r.id AS revision, planner.name AS planner,
       collect(DISTINCT a.title) AS open_tasks
ORDER BY due
"""

CUSTOMER_FIELD = """
MATCH (s:Shipment)-[:SHIPPED_TO]->(:Customer {id:$id})
MATCH (s)-[:OF_REV]->(r:Revision)
RETURN s.id AS id, s.qty AS qty, s.shipped_on AS shipped_on, r.id AS revision, r.status AS status
"""

# Tickets, escalations and conversations that mention the customer, its orders, or its field units.
CUSTOMER_SIGNALS = """
MATCH (c:Customer {id:$id})
MATCH (ch:Chunk)-[:MENTIONS]->(x)
WHERE x = c OR (c)-[:PLACED]->(x)
MATCH (ch)-[:PART_OF]->(s:Source)
OPTIONAL MATCH (s)-[:ASSIGNED_TO]->(who:Person)
RETURN DISTINCT s.id AS source, s.kind AS kind, s.title AS title, s.status AS status, who.name AS assignee,
       max(ch.ts) AS last
ORDER BY last DESC
"""

CUSTOMER_PROJECTS = """
MATCH (pr:Project)-[:COVERS]->(x) WHERE x.id = $id OR (:Customer {id:$id})-[:PLACED]->(x)
OPTIONAL MATCH (lead:Person)-[:LEADS]->(pr)
RETURN DISTINCT pr.id AS id, pr.name AS name, pr.status AS status, lead.name AS lead
"""

ORDER_BOOK = """
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN c.id AS customer, sum(coalesce(o.unit_price, 0) * o.qty) AS value
"""

# Products a ticket or escalation is about, and the projects and firmware leads that can fix them.
FIX_PATH = """
MATCH (s:Source {id:$source})<-[:PART_OF]-(:Chunk)-[:MENTIONS]->(prod:Item {kind:'product'})
MATCH (prod)-[:HAS_REV]->(r:Revision)<-[:COVERS]-(pr:Project)<-[:LEADS]-(lead:Person)
RETURN DISTINCT prod.id AS product, pr.id AS project, pr.name AS project_name, lead.name AS lead
"""

TOP_OF_CHAIN = """
MATCH (p:Person {id:$id})-[:REPORTS_TO*1..4]->(top:Person) WHERE NOT (top)-[:REPORTS_TO]->()
RETURN top.name AS name LIMIT 1
"""


def customer_360(graph: Graph, customer_id: str, escalation: str | None = None) -> dict:
    t = Trace(graph)
    found = t.run("customer", CUSTOMER, {"id": customer_id})
    if not found:
        return {"status": "unknown_customer"}
    cust = found[0]
    orders = t.run("customer_orders", CUSTOMER_ORDERS, {"id": customer_id})
    for o in orders:
        o["value"] = (o["unit_price"] or 0) * o["qty"]
        o["max_penalty"] = round(o["value"] * o["penalty_cap"] / 100) if o["penalty_cap"] else 0
    field = t.run("customer_field", CUSTOMER_FIELD, {"id": customer_id})
    signals = t.run("customer_signals", CUSTOMER_SIGNALS, {"id": customer_id})
    projects = t.run("customer_projects", CUSTOMER_PROJECTS, {"id": customer_id})
    book = t.run("order_book", ORDER_BOOK, {})
    total = sum(b["value"] or 0 for b in book) or 1
    mine = sum(o["value"] for o in orders)
    rank = sorted(book, key=lambda b: -(b["value"] or 0))
    position = next((i + 1 for i, b in enumerate(rank) if b["customer"] == customer_id), None)
    knows = brain.who_knows(graph, customer_id)
    t.steps.extend(knows.pop("trace"))

    actions = []
    esc = escalation or next((s["source"] for s in signals if s["kind"] == "escalation"), None)
    if esc:
        tickets = [s for s in signals if s["kind"] == "ticket" and (s["status"] or "").lower() not in
                   ("closed", "resolved", "done")]
        fix = t.run("fix_path", FIX_PATH, {"source": esc})
        top = (t.run("top_of_chain", TOP_OF_CHAIN, {"id": cust["manager_id"]}) or [{}])[0].get("name") \
            if cust["manager_id"] else None
        next_due = orders[0] if orders else None
        actions.append({"kind": "customer_response", "target": customer_id, "owner": cust["account_manager"],
                        "title": f"Reply to {cust['name']} with a fix plan and dates",
                        "why": "Customer escalation on an open order", "cites": []})
        for tk in tickets:
            actions.append({"kind": "root_cause", "target": tk["source"], "owner": tk["assignee"],
                            "title": f"Confirm root cause and validation plan for {tk['title'].split(':')[0]}",
                            "why": "Open ticket behind the escalation", "cites": []})
        for f in fix:
            actions.append({"kind": "prioritise_fix", "target": f["project"], "owner": f["lead"],
                            "title": f"Decide whether the fix ships in {f['project_name']}",
                            "why": f"{f['project_name']} covers {f['product']}, the product in the escalation",
                            "cites": []})
        if next_due and next_due["build"]:
            actions.append({"kind": "production_hold", "target": next_due["build"], "owner": next_due["planner"],
                            "title": f"Agree acceptance criteria for {next_due['build']} before {next_due['due']}",
                            "why": f"{cust['name']} may hold acceptance of {next_due['id']}", "cites": []})
        if position and position <= 2 and top:
            actions.append({"kind": "executive_brief", "target": customer_id, "owner": top,
                            "title": f"Brief on {cust['name']} (#{position} account, "
                                     f"{round(100 * mine / total)}% of open orders)",
                            "why": "Escalation from a top-two account", "cites": []})

    return {"status": "ok", "customer": cust, "orders": orders, "field_units": field, "signals": signals,
            "projects": projects, "who_knows": knows["people"][:5], "open_value": mine,
            "share_of_book": round(mine / total, 3), "rank": position, "escalation": esc,
            "actions": actions, "trace": t.steps}


CUSTOMERS = """
MATCH (c:Customer)
OPTIONAL MATCH (am:Person)-[:OWNS]->(c)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.id AS id, c.name AS name, am.name AS account_manager, count(o) AS orders,
       sum(coalesce(o.unit_price, 0) * coalesce(o.qty, 0)) AS value
ORDER BY value DESC
"""


# ---------- where the company is fragile ----------

OPERATIONAL = ["Person", "Project", "Item", "Customer", "Order", "Build", "Revision", "Certification"]
OPERATIONAL_RELS = ["OWNS", "WORKS_ON", "LEADS", "COVERS", "CONTAINS", "BUILDS", "FULFILLED_BY", "PLACED",
                    "DEPENDS_ON", "HAS_REV", "CERTIFIES", "BACKS_UP", "REPORTS_TO"]

# FalkorDB estimates betweenness from sampled start nodes. A fixed seed makes one run repeatable; averaging
# several seeded runs (see risk_radar) makes the ranking stable and closer to the exact value.
CHOKEPOINTS = """
CALL algo.betweenness({nodeLabels:$labels, relationshipTypes:$rels, samplingSize:$size, samplingSeed:$seed})
YIELD node, score
WHERE score > 0
RETURN node.id AS id, labels(node)[0] AS label, coalesce(node.name, node.id) AS name, score
"""
CHOKEPOINT_SEEDS = range(1, 11)

COMMUNITIES = """
CALL algo.labelPropagation({nodeLabels:['Person', 'Project', 'Item', 'Customer'],
                            relationshipTypes:['OWNS', 'WORKS_ON', 'LEADS', 'COVERS']})
YIELD node, communityId
OPTIONAL MATCH (node)-[:MEMBER_OF]->(t:Team)
RETURN communityId AS community, collect(node.id) AS members, collect(DISTINCT t.name) AS teams,
       collect(CASE WHEN node:Person THEN node.name END) AS people
"""

SUPPLIERS_PER_PART = """
MATCH (i:Item {kind:'part'})
OPTIONAL MATCH (s:Supplier)-[:QUOTED]->(q:Quote)-[:FOR]->(i) WHERE q.valid_until >= $today
RETURN i.id AS id, i.name AS name, count(DISTINCT s) AS suppliers
"""

ORDER_VALUE_BY_REVISION = """
MATCH (o:Order)-[:FULFILLED_BY]->(:Build)-[:BUILDS]->(r:Revision)
RETURN r.id AS revision, sum(coalesce(o.unit_price, 0) * o.qty) AS value, collect(DISTINCT o.id) AS orders
"""

KNOWLEDGE_SUBJECTS = """
MATCH (x) WHERE (x:Item AND x.kind IN ['part', 'assembly', 'firmware', 'test']) OR x:Project OR x:Customer
RETURN x.id AS id, labels(x)[0] AS label
"""

LOAD = """
MATCH (p:Person)
OPTIONAL MATCH (p)<-[:ASSIGNED_TO]-(a:Action) WHERE coalesce(a.status, 'open') <> 'done'
OPTIONAL MATCH (p)-[:HAS_ABSENCE]->(ab:Absence) WHERE ab.end_date >= $today
RETURN p.id AS id, p.name AS name, count(DISTINCT a) AS open_tasks,
       collect(DISTINCT ab.start_date + ' → ' + ab.end_date) AS upcoming_absence
ORDER BY open_tasks DESC
"""


def risk_radar(graph: Graph, today: date | None = None) -> dict:
    t = Trace(graph)
    today_s = (today or date.today()).isoformat()

    totals: dict[str, dict] = {}
    for seed in CHOKEPOINT_SEEDS:
        for r in t.run(f"chokepoints_seed_{seed}", CHOKEPOINTS,
                       {"labels": OPERATIONAL, "rels": OPERATIONAL_RELS, "size": 1000, "seed": seed}):
            totals.setdefault(r["id"], {**r, "score": 0.0})["score"] += r["score"] / len(CHOKEPOINT_SEEDS)
    chokepoints = sorted(totals.values(), key=lambda r: (-r["score"], r["id"]))[:8]

    value_by_rev = {r["revision"]: r for r in t.run("order_value_by_revision", ORDER_VALUE_BY_REVISION, {})}
    single_source, no_quote = [], []
    for p in t.run("suppliers_per_part", SUPPLIERS_PER_PART, {"today": today_s}):
        if p["suppliers"] > 1:
            continue
        used = [u for u in t.run("where_used", Q.WHERE_USED, {"item_id": p["id"]}) if u["applicable"]]
        if not used:
            continue
        value = sum((value_by_rev.get(u["revision"]) or {}).get("value", 0) for u in used)
        orders = sorted({o for u in used for o in (value_by_rev.get(u["revision"]) or {}).get("orders", [])})
        row = {"id": p["id"], "name": p["name"], "suppliers": p["suppliers"],
               "revisions": [u["revision"] for u in used], "orders": orders, "value_at_risk": value}
        (single_source if p["suppliers"] == 1 else no_quote).append(row)
    single_source.sort(key=lambda s: -s["value_at_risk"])
    no_quote.sort(key=lambda s: -s["value_at_risk"])

    load = t.run("load", LOAD, {"today": today_s})
    away = {p["id"]: p["upcoming_absence"] for p in load if p["upcoming_absence"]}
    bus_factor = []
    for s in t.run("knowledge_subjects", KNOWLEDGE_SUBJECTS, {}):
        k = brain.who_knows(graph, s["id"])
        people = k["people"]
        total = sum(p["score"] for p in people)
        if not people or total < 4:
            continue
        top = people[0]
        share = top["score"] / total
        if share >= 0.6:
            bus_factor.append({"id": s["id"], "label": s["label"], "person": top["name"], "person_id": top["id"],
                               "share": round(share, 2), "away": away.get(top["id"], [])})
    bus_factor.sort(key=lambda b: (-len(b["away"]), -b["share"]))

    book = t.run("order_book", ORDER_BOOK, {})
    total = sum(b["value"] or 0 for b in book) or 1
    concentration = sorted(({"customer": b["customer"], "value": b["value"], "share": round((b["value"] or 0) / total, 3)}
                            for b in book), key=lambda b: -b["value"])

    communities = []
    for c in t.run("communities", COMMUNITIES, {}):
        people = [p for p in c["people"] if p]
        teams = [x for x in c["teams"] if x]
        if len(people) >= 2:
            communities.append({"members": c["members"], "people": people, "teams": teams,
                                "crosses_teams": len(teams) > 1})

    return {"chokepoints": chokepoints, "single_source": single_source, "no_quote": no_quote, "bus_factor": bus_factor,
            "concentration": concentration, "load": load, "communities": communities, "trace": t.steps}


# ---------- incoming signals ----------

SIGNALS = """
MATCH (s:Source) WHERE s.kind IN ['notice', 'escalation', 'leave']
OPTIONAL MATCH (s)<-[:PART_OF]-(c:Chunk)-[:MENTIONS]->(x)
OPTIONAL MATCH (inv:Investigation)-[:TRIGGERED_BY]->(s)
RETURN s.id AS id, s.kind AS kind, s.title AS title, max(c.ts) AS date,
       collect(DISTINCT {id: x.id, label: labels(x)[0]}) AS mentions, inv.id AS investigation
ORDER BY date DESC
"""


def signals(graph: Graph) -> list[dict]:
    out = []
    for s in Trace(graph).run("signals", SIGNALS, {}):
        mentions = [m for m in s["mentions"] if m.get("id")]
        pick = {"notice": "Item", "escalation": "Customer", "leave": "Person"}[s["kind"]]
        subject = None
        if s["kind"] == "notice":
            from neura1.ingest import extract
            import json as _json
            snap = extract.snapshot_path(s["id"], "notice")
            if snap.exists():
                subject = _json.loads(snap.read_text())["output"].get("part")
        # Without an extraction, prefer a record named in the file name (e.g. notice_NB54360_...), then the first mention.
        subject = subject or next((m["id"] for m in mentions if m["label"] == pick and m["id"] in s["id"]), None) \
            or next((m["id"] for m in mentions if m["label"] == pick), None)
        out.append(s | {"subject": subject, "mentions": mentions})
    return out
