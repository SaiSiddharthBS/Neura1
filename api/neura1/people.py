"""People: the full picture of one person, the organisation chart, a personal daily brief, and profile edits.

Everything comes from the graph: reporting lines, teams, projects, work items, decisions, leave, skills, and what
people wrote. Leave details respect `access.Viewer`.
"""

from datetime import date, datetime, timezone

from falkordb import Graph

from neura1 import brain
from neura1.access import Viewer
from neura1.graph import rows
from neura1.impact import Trace

PERSON_CORE = """
MATCH (p:Person {id:$id})
OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (t)-[:PART_OF]->(org:Organization)
OPTIONAL MATCH (p)-[:REPORTS_TO]->(m:Person)
OPTIONAL MATCH (r:Person)-[:REPORTS_TO]->(p)
OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p)
OPTIONAL MATCH (p)-[:BACKS_UP]->(c:Person)
OPTIONAL MATCH (p)-[hr:HOLDS_ROLE]->(o:Organization)
RETURN p.id AS id, p.name AS name, p.role AS role, t.id AS team_id, t.name AS team, org.name AS organization,
       m.id AS manager_id, m.name AS manager,
       collect(DISTINCT {id: r.id, name: r.name, role: r.role}) AS reports,
       collect(DISTINCT {id: b.id, name: b.name}) AS backed_up_by,
       collect(DISTINCT {id: c.id, name: c.name}) AS backs_up,
       collect(DISTINCT {role: hr.role, org: o.name}) AS org_roles
"""

CHAIN = """
MATCH path = (:Person {id:$id})-[:REPORTS_TO*1..6]->(top:Person)
WITH path ORDER BY length(path) DESC LIMIT 1
RETURN [n IN nodes(path) | {id: n.id, name: n.name, role: n.role}] AS chain
"""

WORK = """
MATCH (:Person {id:$id})<-[:ASSIGNED_TO]-(a:Action)
OPTIONAL MATCH (a)-[:IN_PROJECT]->(pr:Project)
OPTIONAL MATCH (inv:Investigation)-[:PRODUCED]->(a)
OPTIONAL MATCH (a)-[:CONCERNS]->(t)
RETURN a.id AS id, a.title AS title, coalesce(a.status, 'open') AS status, a.kind AS kind,
       a.created_at AS created_at, a.completed_at AS completed_at, a.updated_at AS updated_at,
       pr.id AS project_id, pr.name AS project, inv.id AS investigation, inv.kind AS plan_kind, t.id AS target
ORDER BY coalesce(a.completed_at, a.updated_at, a.created_at) DESC
"""

SKILLS = """
MATCH (:Person {id:$id})-[:HAS_SKILL]->(s:Skill)
OPTIONAL MATCH (o:Person)-[:HAS_SKILL]->(s) WHERE o.id <> $id
RETURN s.id AS id, s.name AS name, collect(o.name) AS also
ORDER BY name
"""

ABSENCES = """
MATCH (:Person {id:$id})-[:HAS_ABSENCE]->(a:Absence)
RETURN a.start_date AS start_date, a.end_date AS end_date, a.kind AS kind, a.note AS note ORDER BY start_date
"""


def leave_status(absences: list[dict], today: str) -> dict:
    now = next((a for a in absences if a["start_date"] <= today <= a["end_date"]), None)
    upcoming = [a for a in absences if a["start_date"] > today]
    return {"away_now": bool(now), "current": now, "upcoming": upcoming,
            "past": [a for a in absences if a["end_date"] < today]}


def person_360(graph: Graph, person_id: str, viewer: Viewer, today: date | None = None) -> dict | None:
    t = Trace(graph)
    core = t.run("person_core", PERSON_CORE, {"id": person_id})
    if not core:
        return None
    p = core[0]
    for k in ("reports", "backed_up_by", "backs_up", "org_roles"):
        p[k] = [x for x in p[k] if any(x.values())]
    today_s = (today or date.today()).isoformat()
    chain = (t.run("reporting_chain", CHAIN, {"id": person_id}) or [{"chain": []}])[0]["chain"]
    work = t.run("work", WORK, {"id": person_id})
    absences = t.run("absences", ABSENCES, {"id": person_id})
    leave = leave_status(absences, today_s)
    if not viewer.sees_leave_of(person_id):
        leave = {"away_now": leave["away_now"], "restricted": True}
    profile = brain.person(graph, person_id) or {}
    t.steps.extend(profile.pop("trace", []))
    current = [w for w in work if w["status"] != "done"]
    finished = [w for w in work if w["status"] == "done"]
    return p | {
        "reporting_chain": chain[1:],
        "skills": t.run("skills", SKILLS, {"id": person_id}),
        "work": {"current": current, "finished": finished,
                 "counts": {s: len([w for w in work if w["status"] == s]) for s in ("open", "in_progress", "blocked", "done")}},
        "leave": leave,
        "projects": profile.get("projects", []), "owns": profile.get("owns", []),
        "decisions": profile.get("decisions", []), "topics": profile.get("topics", []),
        "recent": profile.get("recent", []),
        "trace": t.steps,
    }


# ---------- organisation ----------

ORGS = """
MATCH (o:Organization)
OPTIONAL MATCH (o)-[:SUBSIDIARY_OF]->(parent:Organization)
OPTIONAL MATCH (p:Person)-[r:HOLDS_ROLE]->(o)
RETURN o.id AS id, o.name AS name, o.kind AS kind, o.note AS note, parent.id AS parent_id,
       collect(DISTINCT {id: p.id, name: p.name, role: r.role}) AS officers
"""

TEAMS = """
MATCH (t:Team)
OPTIONAL MATCH (t)-[:PART_OF]->(o:Organization)
OPTIONAL MATCH (p:Person)-[:MEMBER_OF]->(t)
RETURN t.id AS id, t.name AS name, o.id AS org_id, collect(DISTINCT {id: p.id, name: p.name, role: p.role}) AS members
ORDER BY name
"""

REPORTING = """
MATCH (p:Person)-[:REPORTS_TO]->(m:Person) RETURN p.id AS person, m.id AS manager
"""

PEOPLE_FLAT = """
MATCH (p:Person)
OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (p)<-[:ASSIGNED_TO]-(a:Action) WHERE coalesce(a.status, 'open') <> 'done'
OPTIONAL MATCH (p)-[:HAS_ABSENCE]->(ab:Absence) WHERE ab.start_date <= $today AND ab.end_date >= $today
RETURN p.id AS id, p.name AS name, p.role AS role, t.id AS team_id, t.name AS team,
       count(DISTINCT a) AS open_work, count(DISTINCT ab) > 0 AS away_now
"""


def org_chart(graph: Graph, today: date | None = None) -> dict:
    t = Trace(graph)
    orgs = t.run("orgs", ORGS, {})
    for o in orgs:
        o["officers"] = [x for x in o["officers"] if x.get("id")]
    return {"organizations": orgs, "teams": [x | {"members": [m for m in x["members"] if m.get("id")]}
                                             for x in t.run("teams", TEAMS, {})],
            "people": t.run("people", PEOPLE_FLAT, {"today": (today or date.today()).isoformat()}),
            "reporting": t.run("reporting", REPORTING, {}), "trace": t.steps}


# ---------- my day ----------

MY_WATCH = """
MATCH (me:Person {id:$id})
OPTIONAL MATCH (me)-[:OWNS]->(o)
OPTIONAL MATCH (me)-[:WORKS_ON|LEADS]->(pr:Project)
OPTIONAL MATCH (pr)-[:COVERS]->(x)
WITH me, collect(DISTINCT o.id) + collect(DISTINCT pr.id) + collect(DISTINCT x.id) AS ids
RETURN [i IN ids WHERE i IS NOT NULL] AS ids
"""

MY_NEWS = """
MATCH (c:Chunk)-[:MENTIONS]->(x) WHERE x.id IN $ids AND c.ts >= $since AND c.retracted_at IS NULL AND NOT c.text STARTS WITH '#'
MATCH (c)-[:PART_OF]->(s:Source)
RETURN DISTINCT c.id AS chunk, s.title AS title, s.kind AS kind, c.author AS author, c.ts AS ts, c.text AS text,
       collect(DISTINCT x.id) AS about
ORDER BY ts DESC LIMIT 12
"""

TEAM_AWAY = """
MATCH (me:Person {id:$id})
OPTIONAL MATCH (me)-[:MEMBER_OF]->(t:Team)<-[:MEMBER_OF]-(colleague:Person)
OPTIONAL MATCH (r:Person)-[:REPORTS_TO*1..4]->(me)
WITH collect(DISTINCT colleague) + collect(DISTINCT r) AS people
UNWIND people AS p
MATCH (p)-[:HAS_ABSENCE]->(a:Absence) WHERE a.end_date >= $today
RETURN DISTINCT p.id AS id, p.name AS name, a.start_date AS start_date, a.end_date AS end_date
ORDER BY start_date
"""


def my_day(graph: Graph, viewer: Viewer, today: date | None = None) -> dict:
    if viewer.unrestricted:
        return {"status": "pick_a_person"}
    from neura1 import scenarios

    t = Trace(graph)
    today_d = today or date.today()
    me = person_360(graph, viewer.id, viewer, today_d)
    t.steps.extend(me.pop("trace", []))
    ids = (t.run("my_watch", MY_WATCH, {"id": viewer.id}) or [{"ids": []}])[0]["ids"]
    since = date.fromordinal(today_d.toordinal() - 45).isoformat()
    news = t.run("my_news", MY_NEWS, {"ids": ids, "since": since})
    signals = [s for s in scenarios.signals(graph)
               if s["subject"] in ids or s["subject"] == viewer.id or any(m["id"] in ids for m in s["mentions"])]
    away = t.run("team_away", TEAM_AWAY, {"id": viewer.id, "today": today_d.isoformat()})
    away = [a for a in away if viewer.sees_leave_of(a["id"])]
    approvals = [w for w in me["work"]["current"] if w["kind"] in ("confirm_handover", "interim_lead",
                                                                    "executive_brief", "engineering_review")]
    return {"status": "ok", "me": me, "watching": ids, "news": news, "signals": signals, "team_away": away,
            "approvals": approvals, "trace": t.steps}


# ---------- profile edits ----------

def update_person(graph: Graph, person_id: str, changes: dict, by: str) -> dict:
    """Change role, team, manager or backup. Each change is kept as an Event so the history stays in the graph."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not rows(graph, "MATCH (p:Person {id:$id}) RETURN p.id AS id", {"id": person_id}):
        raise KeyError(person_id)
    if "name" in changes or "role" in changes:
        graph.query("MATCH (p:Person {id:$id}) SET p.name = coalesce($name, p.name), p.role = coalesce($role, p.role)",
                    {"id": person_id, "name": changes.get("name"), "role": changes.get("role")})
    if "team_id" in changes:
        graph.query("""MATCH (p:Person {id:$id}) OPTIONAL MATCH (p)-[old:MEMBER_OF]->() DELETE old
                       WITH DISTINCT p MATCH (t:Team {id:$team}) MERGE (p)-[:MEMBER_OF]->(t)""",
                    {"id": person_id, "team": changes["team_id"]})
    if "manager_id" in changes:
        graph.query("""MATCH (p:Person {id:$id}) OPTIONAL MATCH (p)-[old:REPORTS_TO]->() DELETE old
                       WITH DISTINCT p MATCH (m:Person {id:$m}) WHERE m <> p MERGE (p)-[:REPORTS_TO]->(m)""",
                    {"id": person_id, "m": changes["manager_id"]})
    if "backup_id" in changes:
        graph.query("""MATCH (p:Person {id:$id}) OPTIONAL MATCH ()-[old:BACKS_UP]->(p) DELETE old
                       WITH DISTINCT p MATCH (b:Person {id:$b}) WHERE b <> p MERGE (b)-[:BACKS_UP]->(p)""",
                    {"id": person_id, "b": changes["backup_id"]})
    for skill in changes.get("add_skills", []):
        graph.query("""MATCH (p:Person {id:$id}) MERGE (s:Skill {name:$s})
                       ON CREATE SET s.id = 'SK-' + toUpper(replace($s, ' ', '-'))
                       MERGE (p)-[:HAS_SKILL]->(s)""", {"id": person_id, "s": skill.strip()})
    for skill in changes.get("remove_skills", []):
        graph.query("MATCH (:Person {id:$id})-[h:HAS_SKILL]->(:Skill {name:$s}) DELETE h", {"id": person_id, "s": skill})
    if changes.get("absence"):
        a = changes["absence"]
        graph.query("""MATCH (p:Person {id:$id})
                       MERGE (x:Absence {id:$id + ':' + $a.start_date})
                       SET x.start_date=$a.start_date, x.end_date=$a.end_date, x.kind=coalesce($a.kind, 'leave'),
                           x.note=$a.note
                       MERGE (p)-[:HAS_ABSENCE]->(x)""", {"id": person_id, "a": a})
    graph.query("""MATCH (p:Person {id:$id})
                   CREATE (e:Event {kind:'profile_change', at:$now, by:$by, detail:$detail})-[:ON]->(p)""",
                {"id": person_id, "now": now, "by": by,
                 "detail": ", ".join(f"{k}={v}" for k, v in changes.items() if v not in (None, [], ""))})
    return {"id": person_id, "updated": sorted(k for k, v in changes.items() if v not in (None, [], ""))}


def add_person(graph: Graph, person_id: str, name: str, role: str, team_id: str | None, by: str) -> dict:
    if rows(graph, "MATCH (p:Person {id:$id}) RETURN p.id AS id", {"id": person_id}):
        raise ValueError(f"{person_id} already exists")
    graph.query("CREATE (p:Person {id:$id, name:$name, role:$role, authority:'approved', source:'neura1'})",
                {"id": person_id, "name": name, "role": role})
    return update_person(graph, person_id, {"team_id": team_id} if team_id else {}, by)
