"""Timeline: every project, task, build and customer order on one Gantt, with the deviation from the plan.

Three dates are kept for everything on the timeline:
  * baseline: the first plan recorded (an import or ERP sync that later moves a date keeps the original here);
  * plan: the date the system of record holds now;
  * forecast: what the graph says will really happen, worked out by code, never by the model.

Forecast rules (each one is listed in the response, so a reader can check them):
  * builds: free stock and open purchase orders go to builds in date order; a part still short must be ordered today
    and arrives after its lead time by the newest information (a supplier notice beats a quote, a quote beats order
    history). A build whose parts arrive after its planned date finishes three weeks after the last one arrives
    (assembly, test and dispatch: the same assumption as "Can we promise");
  * customer orders ship when the build that fulfils them finishes, never before their due date;
  * tasks: done tasks keep their real finish; an open task past its due date is due today at the earliest; leave in
    the task's remaining window pushes it out by the working days lost (leave is only weighed for readers allowed to
    see it);
  * projects finish when the last of their tasks, builds and orders finishes, never before the target.
Deviation is forecast minus baseline, in days: positive is late.
"""

from datetime import date, timedelta

from falkordb import Graph

from neura1 import promise, supply
from neura1.access import Viewer
from neura1.graph import rows

DEFAULT_BUILD_DAYS = 21  # a build with no customer order recorded: assembly, test and dispatch (an assumption, shown)
RISK_DAYS = 5  # a forecast this close to the plan is still on track, but flagged

PLAN_PROJECTS = """
MATCH (p:Project)
OPTIONAL MATCH (lead:Person)-[:LEADS]->(p)
RETURN p.id AS id, p.name AS name, p.status AS status, p.start_date AS start, p.target_date AS target,
       coalesce(p.baseline_target, p.target_date) AS baseline_target, lead.name AS lead
ORDER BY p.target_date, p.id
"""

PLAN_TASKS = """
MATCH (a:Action {kind:'work'})
OPTIONAL MATCH (a)-[:IN_PROJECT]->(p:Project)
OPTIONAL MATCH (a)-[:ASSIGNED_TO]->(who:Person)
RETURN a.id AS id, a.title AS title, a.status AS status, a.start_date AS start, a.due_date AS due,
       coalesce(a.baseline_start, a.start_date) AS baseline_start, coalesce(a.baseline_due, a.due_date) AS baseline_due,
       a.created_at AS created, a.completed_at AS completed, a.target AS target, p.id AS project,
       who.id AS person_id, who.name AS owner
ORDER BY a.id
"""

PLAN_BUILDS = """
MATCH (b:Build)-[:BUILDS]->(r:Revision)
OPTIONAL MATCH (o:Order)-[:FULFILLED_BY]->(b)
OPTIONAL MATCH (c:Customer)-[:PLACED]->(o)
OPTIONAL MATCH (owner:Person)-[:OWNS]->(b)
OPTIONAL MATCH (pr:Project)-[:COVERS]->(b)
RETURN b.id AS id, r.id AS revision, b.qty AS qty, b.status AS status, b.planned_date AS planned,
       coalesce(b.baseline_date, b.planned_date) AS baseline, owner.name AS owner,
       collect(DISTINCT pr.id) AS projects,
       collect(DISTINCT {id:o.id, due:o.due_date, qty:o.qty, customer:c.name, penalty_note:o.penalty_note,
                         unit_price:o.unit_price, penalty_pct:o.penalty_pct_per_week, cap_pct:o.penalty_cap_pct}) AS orders
ORDER BY planned, id
"""

ORDER_PROJECTS = "MATCH (pr:Project)-[:COVERS]->(o:Order) RETURN o.id AS id, collect(pr.id) AS projects"

OPEN_POS = """
MATCH (po:PurchaseOrder)-[:ORDERS]->(:Item {id:$id})
WHERE po.status IN ['open', 'partially_received']
OPTIONAL MATCH (g:Receipt)-[:AGAINST]->(po)
WITH po, sum(coalesce(g.qty, 0)) AS received
RETURN po.id AS id, po.qty - received AS qty, po.expected_on AS expected
ORDER BY expected
"""

ABSENCES = """
MATCH (p:Person {id:$id})-[:HAS_ABSENCE]->(a:Absence) WHERE a.end_date >= $from AND a.start_date <= $to
RETURN a.start_date AS start, a.end_date AS end ORDER BY start
"""


def _d(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def workdays(start: date, end: date) -> int:
    """Monday to Friday between two dates, both included."""
    if end < start:
        return 0
    return sum(1 for i in range((end - start).days + 1) if (start + timedelta(days=i)).weekday() < 5)


def add_workdays(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _days(a: date | None, b: date | None) -> int | None:
    return (a - b).days if a and b else None


def _state(deviation: int | None, done: bool, risky: bool) -> str:
    if deviation is None:
        return "unscheduled"
    if done:
        return "done_late" if deviation > 0 else "done"
    if deviation > 0:
        return "late"
    return "at_risk" if risky else "on_track"


# ---------- builds: parts arrive in date order ----------

def build_forecasts(graph: Graph, builds: list[dict], today: date) -> dict[str, dict]:
    """For each open build: when its parts are really there, and which part decides it."""
    notes = supply.notices(graph)
    ready: dict[str, list[tuple[date | None, str, str]]] = {b["id"]: [] for b in builds}
    parts: dict[str, list[tuple[dict, dict]]] = {}
    for b in builds:
        if b["status"] == "done":
            continue
        for p in supply.explode(graph, b["revision"]):
            parts.setdefault(p["id"], []).append((p, b))
    for pid, uses in parts.items():
        first = uses[0][0]
        recorded = first["on_hand"] >= 0
        pool = max(first["on_hand"] - first["allocated"], 0) if recorded else 0
        arrivals = [(_d(po["expected"]) or date.max, int(po["qty"] or 0), po["id"])
                    for po in rows(graph, OPEN_POS, {"id": pid}) if (po["qty"] or 0) > 0]
        lead = None
        for p, b in sorted(uses, key=lambda u: u[1]["planned"] or ""):
            planned = _d(b["planned"]) or today
            pool += sum(q for when, q, _ in arrivals if when <= planned)
            arrivals = [a for a in arrivals if a[0] > planned]
            need = int(p["per_unit"]) * int(b["qty"] or 0)
            take = min(pool, need)
            pool -= take
            short = need - take
            if not short:
                continue
            # Later purchase orders already placed cover what they can, in date order.
            when = None
            while short and arrivals:
                when, q, po = arrivals[0]
                used = min(q, short)
                short -= used
                arrivals[0] = (when, q - used, po)
                if arrivals[0][1] == 0:
                    arrivals.pop(0)
            if short:
                lead = lead or supply.lead_time(graph, pid, today, notes.get(pid))
                if lead["weeks"] is None:
                    ready[b["id"]].append((None, pid, f"{pid}: short {short} and no lead time is on record"))
                    continue
                arrive = supply.weeks(today, lead["weeks"])
                basis = {"notice": "the supplier notice", "quote": f"quote {lead['source']}",
                         "history": "recent orders"}.get(lead["basis"], lead["basis"])
                ready[b["id"]].append((arrive, pid, f"{pid}: short {short} of {need}; ordered today it arrives "
                                                    f"{arrive.isoformat()} ({lead['weeks']} weeks by {basis})"))
            elif when:
                ready[b["id"]].append((when, pid, f"{pid}: covered by an open purchase order arriving "
                                                  f"{when.isoformat()}"))
    out = {}
    for b in builds:
        planned = _d(b["planned"])
        found = ready.get(b["id"], [])
        unknown = [r for r in found if r[0] is None]
        dated = [r for r in found if r[0] is not None and planned and r[0] > planned]
        driver = max(dated, default=None)
        out[b["id"]] = {"start": driver[0] if driver else planned, "driver": driver[1] if driver else None,
                        "reasons": [r[2] for r in sorted(dated, reverse=True)] + [r[2] for r in unknown],
                        "unknown": bool(unknown)}
    return out


def _after_leave(graph: Graph, person: str, window_start: date, end: date) -> tuple[date, list]:
    """The task needs the working days it has left; days on leave do not count, so the finish moves out."""
    found = rows(graph, ABSENCES, {"id": person, "from": window_start.isoformat(),
                                   "to": (end + timedelta(days=366)).isoformat()})
    spans = [(a, _d(a["start"]), _d(a["end"])) for a in found]
    left = workdays(window_start, end)
    d = window_start - timedelta(days=1)
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and not any(s <= d <= e for _, s, e in spans):
            left -= 1
    finish = max(end, d)
    away = [(a, lost) for a, s, e in spans if (lost := workdays(max(s, window_start), min(e, finish)))]
    return finish, away


# ---------- the timeline ----------

def timeline(graph: Graph, viewer: Viewer, today: date | None = None) -> dict:
    today = today or date.today()
    projects = rows(graph, PLAN_PROJECTS)
    tasks = rows(graph, PLAN_TASKS)
    builds = rows(graph, PLAN_BUILDS)
    order_projects = {r["id"]: r["projects"] for r in rows(graph, ORDER_PROJECTS)}
    forecasts = build_forecasts(graph, builds, today)
    items: list[dict] = []
    slip_of: dict[str, int] = {}

    for b in builds:
        f = forecasts[b["id"]]
        plan_start, base_start = _d(b["planned"]), _d(b["baseline"])
        orders = [o for o in b["orders"] if o.get("id")]
        dues = [_d(o["due"]) for o in orders if _d(o["due"])]
        length = (min(dues) - plan_start).days if dues and plan_start and min(dues) > plan_start else DEFAULT_BUILD_DAYS
        start = f["start"] or plan_start
        slip = max(_days(start, plan_start) or 0, 0)
        done = b["status"] == "done"
        plan_end = plan_start + timedelta(days=length) if plan_start else None
        end = max(plan_end, start + timedelta(weeks=promise.BUILD_WEEKS)) if slip and plan_end else plan_end
        slip_of[b["id"]] = 0 if done else max(_days(end, plan_end) or 0, 0)
        base_end = base_start + timedelta(days=length) if base_start else None
        deviation = _days(end, base_end)
        reasons = list(f["reasons"])
        if f["unknown"]:
            reasons.append("The forecast is not confirmed: a part has no lead time on record.")
        items.append({
            "id": b["id"], "kind": "build", "title": f"Build {b['id']}: {b['qty']} × {b['revision']}",
            "owner": b["owner"], "status": b["status"], "projects": b["projects"],
            "baseline": {"start": _iso(base_start), "end": _iso(base_end)},
            "plan": {"start": _iso(plan_start), "end": _iso(plan_end)},
            "forecast": {"start": _iso(start), "end": _iso(end)},
            "deviation_days": deviation, "driver": f["driver"], "reasons": reasons,
            "state": "unconfirmed" if f["unknown"] and not done else _state(deviation, done, False),
            "links": [o["id"] for o in orders]})
        for o in orders:
            due = _d(o["due"])
            o_end = max(due, end) if due and end and slip_of[b["id"]] else due
            o_dev = _days(o_end, due)
            why = ([f"Fulfilled by {b['id']}, which is forecast to finish {_iso(end)}."] if o_dev else [])
            row = {"id": o["id"], "kind": "order", "title": f"{o['id']}: {o['qty']} units for {o['customer']}",
                   "owner": None, "status": "open", "projects": order_projects.get(o["id"], []),
                   "baseline": {"start": None, "end": o["due"]}, "plan": {"start": None, "end": o["due"]},
                   "forecast": {"start": None, "end": _iso(o_end)}, "deviation_days": o_dev, "driver": b["id"] if slip else None,
                   "reasons": why, "state": _state(o_dev, False, False), "links": [b["id"]], "milestone": True}
            if viewer.sees_money and o_dev and o_dev > 0 and o.get("penalty_pct"):
                late_weeks = -(-o_dev // 7)
                pct = min(late_weeks * o["penalty_pct"], o["cap_pct"] or late_weeks * o["penalty_pct"])
                row["penalty"] = {"note": o["penalty_note"], "weeks_late": late_weeks, "pct": pct,
                                  "per_week_pct": o["penalty_pct"], "capped": bool(o["cap_pct"]) and pct >= o["cap_pct"],
                                  "value": round(pct / 100 * (o["unit_price"] or 0) * (o["qty"] or 0))}
            items.append(row)

    late_targets = {i["id"]: i for i in items if i["state"] in ("late", "unconfirmed")}
    for t in tasks:
        start, due = _d(t["start"]), _d(t["due"])
        base_start, base_due = _d(t["baseline_start"]), _d(t["baseline_due"])
        done = t["status"] == "done"
        reasons: list[str] = []
        risky = t["status"] == "blocked"
        if risky:
            reasons.append("Marked blocked in the tracker.")
        if done:
            end = _d(t["completed"]) or due
        else:
            end = due
            if due and due < today:
                end = today
                reasons.append(f"Still {t['status'].replace('_', ' ')} {(today - due).days} days after its due date.")
            if due and t["person_id"] and viewer.sees_leave_of(t["person_id"]):
                end, away = _after_leave(graph, t["person_id"], max(start or today, today), end)
                for a, lost in away:
                    reasons.append(f"{t['owner']} is away {a['start']} to {a['end']}: {lost} working days of this "
                                   f"task fall in it.")
        if base_due and due and base_due != due:
            reasons.append(f"Replanned: due {due.isoformat()}, originally {base_due.isoformat()} "
                           f"({'+' if due > base_due else ''}{(due - base_due).days} days).")
        linked = None if done else late_targets.get(t["target"] or "")
        if linked:
            risky = True
            reasons.append(f"Works on {linked['id']}, which is forecast {linked['deviation_days'] or 0} days late.")
        deviation = _days(end, base_due)
        items.append({
            "id": t["id"], "kind": "task", "title": t["title"], "owner": t["owner"], "status": t["status"],
            "projects": [t["project"]] if t["project"] else [],
            "baseline": {"start": _iso(base_start), "end": _iso(base_due)},
            "plan": {"start": _iso(start), "end": _iso(due)},
            "forecast": {"start": _iso(start), "end": _iso(end)},
            "deviation_days": deviation, "driver": linked["id"] if linked else None, "reasons": reasons,
            "state": _state(deviation, done, risky or (deviation is not None and -RISK_DAYS < deviation <= 0
                                                        and not done and bool(reasons))),
            "links": [t["target"]] if t["target"] else []})

    groups = []
    for p in projects:
        members = [i for i in items if p["id"] in i["projects"]]
        target, base = _d(p["target"]), _d(p["baseline_target"])
        ends = [(_d(i["forecast"]["end"]), i) for i in members if _d(i["forecast"]["end"])]
        latest = max(ends, key=lambda e: e[0], default=None)
        end = max(target, latest[0]) if target and latest else target
        deviation = _days(end, base)
        driver = latest[1] if latest and target and latest[0] > target else None
        late = [i for i in members if i["state"] in ("late", "done_late", "unconfirmed")]
        groups.append({
            "id": p["id"], "name": p["name"], "lead": p["lead"], "status": p["status"],
            "baseline": {"start": p["start"], "end": p["baseline_target"]},
            "plan": {"start": p["start"], "end": p["target"]},
            "forecast": {"start": p["start"], "end": _iso(end)}, "deviation_days": deviation,
            "state": _state(deviation, p["status"] == "done", bool(late)),
            "driver": driver["id"] if driver else None,
            "reasons": ([f"{driver['id']} finishes {driver['forecast']['end']}, after the target {p['target']}."]
                        if driver else []) + ([f"{len(late)} item{'s' if len(late) > 1 else ''} late."] if late else []),
            "items": sorted(members, key=lambda i: (i["plan"]["start"] or i["plan"]["end"] or "", i["id"]))})
    for gid, name, kinds in (("production", "Other builds and customer orders", ("build", "order")),
                             ("other", "Other work", ("task",))):
        loose = [i for i in items if not i["projects"] and i["kind"] in kinds]
        if loose:
            late = [i for i in loose if i["state"] in ("late", "done_late", "unconfirmed")]
            groups.append({"id": gid, "name": name, "lead": None, "status": "active",
                           "baseline": {"start": None, "end": None}, "plan": {"start": None, "end": None},
                           "forecast": {"start": None, "end": None}, "deviation_days": None,
                           "state": "late" if any(i["state"] == "late" for i in late) else "unscheduled",
                           "driver": None, "reasons": [f"{len(late)} item{'s' if len(late) > 1 else ''} late."] if late else [],
                           "items": sorted(loose, key=lambda i: (i["plan"]["start"] or i["plan"]["end"] or "", i["id"]))})

    dated = [d for i in items + groups for k in ("baseline", "plan", "forecast") for d in (i[k]["start"], i[k]["end"]) if d]
    late_items = sorted((i for i in items if i["state"] == "late"), key=lambda i: -(i["deviation_days"] or 0))
    return {
        "today": today.isoformat(),
        "range": {"start": min(dated, default=today.isoformat()), "end": max(dated, default=today.isoformat())},
        "summary": {"items": len(items), "late": len(late_items),
                    "done_late": sum(1 for i in items if i["state"] == "done_late"),
                    "at_risk": sum(1 for i in items if i["state"] in ("at_risk", "unconfirmed")),
                    "projects_late": sum(1 for g in groups if (g["deviation_days"] or 0) > 0),
                    "worst": [{"id": i["id"], "title": i["title"], "deviation_days": i["deviation_days"],
                               "reason": (i["reasons"] or [""])[0]} for i in late_items[:3]]},
        "groups": groups,
        "leave_included": viewer.unrestricted or viewer.leader,
        "rules": [
            "Baseline is the first plan recorded; plan is the date held now; forecast is worked out from the graph.",
            "Builds: free stock and open purchase orders go to builds in date order; a part still short is ordered "
            "today and arrives after its lead time (a supplier notice beats a quote, a quote beats order history).",
            "Customer orders slip by as many days as the build that fulfils them.",
            "Tasks: done tasks keep their real finish; open tasks past due are due today at the earliest; leave in "
            "the remaining window adds the working days lost.",
            f"A build with no customer order is assumed to take {DEFAULT_BUILD_DAYS} days.",
            "Projects finish when their last task, build or order finishes, never before the target.",
            "Deviation = forecast end minus baseline end, in days; positive is late.",
        ],
    }
