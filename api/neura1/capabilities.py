"""Capability map: what Flyvi can do, built from recorded work, with people analytics handled carefully.

Evidence, not ratings. A person's expertise is the work they actually did: tasks they finished (hands-on) and tasks they
are doing now (involved), each tagged with the skills it needs. Self-declared skills are shown separately as "stated".
There are no scores, percentages or rankings anywhere in this module.

Tags: the model reads each task and project and picks skills only from Flyvi's own skill list; anything else is
rejected by code. Tags are snapshotted (fixture/flyvi/extracted/skill_tags.json) like other model output, so a load
is reproducible. Tasks created later without tags fall back to a fixed mapping by task kind.

Who sees what (same graph-derived rules as money and leave):
- a person's full expertise: the person, and the directors and leadership team; everyone else sees stated skills;
- the company map: everyone sees areas, counts and gaps; names in the people grid only for the directors and the
  leadership team.
"""

import json
from datetime import date, datetime, timedelta, timezone

from falkordb import Graph

from neura1.access import Viewer
from neura1.config import settings
from neura1.graph import rows

TAGS_FILE = "extracted/skill_tags.json"

AREAS: dict[str, list[str]] = {
    "Power electronics": ["Power stage design", "Thermal derating", "DC-DC converters", "Schematic and PCB design",
                          "Power electronics architecture", "MIL-STD-704"],
    "Firmware and software": ["Embedded C", "Power sequencing", "CAN bus", "Bootloaders", "Field firmware updates",
                              "Digital control loops", "Battery management firmware", "Python", "Desktop tools and GUI",
                              "Data logging"],
    "Test and quality": ["Test automation", "Requirements traceability", "MIL-STD-461 EMI/EMC testing",
                         "Environmental testing", "Functional testing", "AS9100D", "Configuration management"],
    "Supply chain and production": ["Component sourcing", "Obsolescence management", "Inventory control",
                                    "Production planning", "Assembly and soldering"],
    "Customers and programmes": ["Defence customer accounts", "System integration", "Project planning"],
    "People and operations": ["HR policies"],
}
AREA_OF = {s: a for a, ss in AREAS.items() for s in ss}

# Tasks created by plans (not tagged by the model) still count, through what kind of work they are.
KIND_SKILLS = {
    "engineering_review": ["Power electronics architecture"],
    "firmware_review": ["Embedded C", "Power sequencing"],
    "requalification": ["Thermal derating", "Functional testing"],
    "procurement": ["Component sourcing", "Obsolescence management"],
    "production_replan": ["Production planning"],
    "customer_comms": ["Defence customer accounts"],
    "customer_response": ["Defence customer accounts"],
    "root_cause": ["System integration"],
}

# ---------- tagging (model, verified) ----------

TAG_SCHEMA = {
    "type": "object",
    "properties": {"tags": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "skills": {"type": "array", "items": {"type": "string"}}}, "required": ["id", "skills"]}}},
    "required": ["tags"],
}
TAG_SYSTEM = """You tag work at Flyvi Technologies, a maker of power and control electronics for defence and rail.
For each record, choose the 1 to 3 skills from SKILLS that a person needs to do it. Use the exact skill names given.
If none fits, return an empty list. Return JSON {"tags": [{"id", "skills"}]} with every record id."""


def skill_vocabulary(graph: Graph) -> list[str]:
    return [r["name"] for r in rows(graph, "MATCH (s:Skill) RETURN s.name AS name ORDER BY name")]


def records_to_tag(graph: Graph) -> list[dict]:
    tasks = rows(graph, """
        MATCH (a:Action) WHERE a.id STARTS WITH 'WRK-'
        OPTIONAL MATCH (a)-[:IN_PROJECT]->(p:Project)
        RETURN a.id AS id, a.title + coalesce(' (project: ' + p.name + ')', '') + coalesce(' about ' + a.target, '') AS text
        ORDER BY id""")
    projects = rows(graph, "MATCH (p:Project) RETURN p.id AS id, p.name + ': ' + coalesce(p.summary, '') AS text ORDER BY id")
    return tasks + projects


def verify_tags(raw: list[dict], vocabulary: list[str], ids: set[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Keep only known record ids and skills from Flyvi's list (case-insensitive); report everything rejected."""
    canon = {v.lower(): v for v in vocabulary}
    kept: dict[str, list[str]] = {}
    rejected: dict[str, list[str]] = {}
    for t in raw:
        rid = str(t.get("id", "")).strip()
        if rid not in ids:
            rejected.setdefault("_unknown_records", []).append(rid)
            continue
        good, bad = [], []
        for s in t.get("skills", [])[:3]:
            (good if str(s).strip().lower() in canon else bad).append(canon.get(str(s).strip().lower(), str(s)))
        kept[rid] = sorted(set(good))
        if bad:
            rejected[rid] = bad
    return kept, rejected


def tag_with_model(graph: Graph, batch: int = 12) -> dict:
    from neura1.llm import chat_json

    vocabulary = skill_vocabulary(graph)
    records = records_to_tag(graph)
    ids = {r["id"] for r in records}
    raw: list[dict] = []
    for i in range(0, len(records), batch):
        chunk = records[i:i + batch]
        user = "SKILLS:\n" + "\n".join(f"- {v}" for v in vocabulary) + "\n\nRECORDS:\n" + \
               "\n".join(f"[{r['id']}] {r['text']}" for r in chunk)
        raw += chat_json(TAG_SYSTEM, user, TAG_SCHEMA, "skill_tags").get("tags", [])
    kept, rejected = verify_tags(raw, vocabulary, ids)
    from neura1 import llm as _llm
    snap = {"model": _llm.last_model or settings.llm_model, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tags": kept, "rejected": rejected}
    (settings.fixture_dir / TAGS_FILE).write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return snap


def load_tags(graph: Graph) -> int:
    path = settings.fixture_dir / TAGS_FILE
    if not path.exists():
        return 0
    snap = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for rid, skills in snap["tags"].items():
        for s in skills:
            r = rows(graph, """
                MATCH (x {id:$id}) WHERE x:Action OR x:Project MATCH (s:Skill {name:$s})
                MERGE (x)-[t:NEEDS_SKILL]->(s) SET t.by = 'model', t.model = $m, t.authority = 'extracted'
                RETURN count(t) AS n""", {"id": rid, "s": s, "m": snap.get("model")}, read_only=False)
            n += r[0]["n"] if r else 0
    return n


# ---------- evidence ----------

TASK_SKILLS = """
MATCH (a:Action)
OPTIONAL MATCH (a)-[:NEEDS_SKILL]->(s:Skill)
OPTIONAL MATCH (a)-[:ASSIGNED_TO]->(p:Person)
RETURN a.id AS id, a.title AS title, a.kind AS kind, coalesce(a.status, 'open') AS status,
       coalesce(a.completed_at, a.created_at) AS at, p.id AS person, p.name AS name, collect(s.name) AS skills
"""


def _task_skills(graph: Graph) -> list[dict]:
    out = []
    for t in rows(graph, TASK_SKILLS):
        skills = t["skills"] or KIND_SKILLS.get(t["kind"] or "", [])
        out.append({**t, "skills": sorted(set(skills))})
    return out


def person_expertise(graph: Graph, person_id: str, viewer: Viewer) -> dict:
    stated = [r["name"] for r in rows(graph, "MATCH (:Person {id:$id})-[:HAS_SKILL]->(s:Skill) RETURN s.name AS name "
                                            "ORDER BY name", {"id": person_id})]
    if not viewer.sees_profile_of(person_id):
        return {"restricted": True, "stated": stated,
                "note": "Expertise from work is visible to the person, and to the directors and leadership team."}
    by_skill: dict[str, dict] = {}
    for t in _task_skills(graph):
        if t["person"] != person_id:
            continue
        for s in t["skills"]:
            e = by_skill.setdefault(s, {"skill": s, "area": AREA_OF.get(s, "Other"), "finished": [], "current": []})
            (e["finished"] if t["status"] == "done" else e["current"]).append({"id": t["id"], "title": t["title"], "at": t["at"]})
    for s in stated:
        by_skill.setdefault(s, {"skill": s, "area": AREA_OF.get(s, "Other"), "finished": [], "current": []})
    skills = []
    for e in by_skill.values():
        level = "hands-on" if e["finished"] else "involved" if e["current"] else "stated"
        skills.append({**e, "level": level, "stated": e["skill"] in stated})
    order = {"hands-on": 0, "involved": 1, "stated": 2}
    skills.sort(key=lambda e: (order[e["level"]], e["area"], e["skill"]))
    return {"restricted": False, "skills": skills, "stated": stated}


def company_map(graph: Graph, viewer: Viewer, today: date | None = None) -> dict:
    today = today or date.today()
    soon = (today + timedelta(days=60)).isoformat()
    tasks = _task_skills(graph)
    people = {r["id"]: r for r in rows(graph, """
        MATCH (p:Person) OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
        OPTIONAL MATCH (p)-[:HAS_SKILL]->(s:Skill)
        RETURN p.id AS id, p.name AS name, t.name AS team, collect(s.name) AS stated""")}
    away = {r["id"] for r in rows(graph, """
        MATCH (p:Person)-[:HAS_ABSENCE]->(a:Absence) WHERE a.end_date >= $today AND a.start_date <= $soon
        RETURN DISTINCT p.id AS id""", {"today": today.isoformat(), "soon": soon})}
    project_needs = rows(graph, """
        MATCH (p:Project)-[:NEEDS_SKILL]->(s:Skill) WHERE coalesce(p.status, 'active') IN ['active', 'design', 'planning']
        RETURN s.name AS skill, collect(p.name) AS projects""")
    proj_by_skill = {r["skill"]: r["projects"] for r in project_needs}

    skills = {}
    for name in [r["name"] for r in rows(graph, "MATCH (s:Skill) RETURN s.name AS name")]:
        skills[name] = {"skill": name, "area": AREA_OF.get(name, "Other"), "hands_on": set(), "involved": set(),
                        "stated": {pid for pid, p in people.items() if name in p["stated"]},
                        "open_tasks": [], "finished_tasks": 0, "projects": proj_by_skill.get(name, [])}
    for t in tasks:
        for s in t["skills"]:
            e = skills.get(s)
            if not e:
                continue
            if t["status"] == "done":
                e["finished_tasks"] += 1
                if t["person"]:
                    e["hands_on"].add(t["person"])
            else:
                e["open_tasks"].append({"id": t["id"], "title": t["title"], "owner": t["name"]})
                if t["person"]:
                    e["involved"].add(t["person"])

    def names_visible(pid: str) -> bool:
        return viewer.unrestricted or viewer.leader or pid in viewer.reports or pid == viewer.id

    out_skills, areas = [], {}
    for e in skills.values():
        hands_on = sorted(e["hands_on"])
        anyone = e["hands_on"] | e["involved"] | e["stated"]
        demand = len(e["open_tasks"]) + len(e["projects"])
        # gap: work needs it and nobody has it at any level; unproven: people are on it but nobody has finished
        # work in it yet; thin: one person holds it; covered: more than one.
        if not demand:
            status = "idle"
        elif not anyone:
            status = "gap"
        elif not hands_on:
            status = "unproven"
        elif len(anyone) == 1:
            status = "thin"
        else:
            status = "covered"
        away_n = len([p for p in hands_on if p in away])
        row = {
            "skill": e["skill"], "area": e["area"], "status": status,
            "hands_on": len(hands_on), "involved": len(e["involved"] - e["hands_on"]), "stated": len(e["stated"]),
            "open_tasks": len(e["open_tasks"]), "projects": e["projects"], "finished_tasks": e["finished_tasks"],
            "away_soon": away_n if viewer.unrestricted or viewer.leader else None,
            "people": [{"id": p, "name": people[p]["name"], "level": "hands-on"} for p in hands_on if names_visible(p)]
                      + [{"id": p, "name": people[p]["name"], "level": "involved"} for p in sorted(e["involved"] - e["hands_on"])
                         if names_visible(p)],
            "examples": [x["title"] for x in e["open_tasks"][:3]],
        }
        out_skills.append(row)
        a = areas.setdefault(e["area"], {"area": e["area"], "skills": 0, "people": set(), "active": set(), "open_tasks": 0,
                                         "finished_tasks": 0, "gaps": 0, "thin": 0, "unproven": 0})
        a["skills"] += 1
        a["people"] |= e["hands_on"]
        a["active"] |= e["involved"] | e["hands_on"]
        a["unproven"] += status == "unproven"
        a["open_tasks"] += len(e["open_tasks"])
        a["finished_tasks"] += e["finished_tasks"]
        a["gaps"] += status == "gap"
        a["thin"] += status == "thin"
    area_rows = []
    for a in areas.values():
        trend = "growing" if a["open_tasks"] > a["finished_tasks"] else "steady" if a["open_tasks"] else "quiet"
        area_rows.append({**a, "people": len(a["people"]), "active": len(a["active"]), "trend": trend})
    area_rows.sort(key=lambda a: (-(a["open_tasks"] + a["finished_tasks"]), a["area"]))
    rank = {"gap": 0, "thin": 1, "unproven": 2, "covered": 3, "idle": 4}
    out_skills.sort(key=lambda s: (rank[s["status"]], -s["open_tasks"], s["skill"]))
    grid_names = viewer.unrestricted or viewer.leader or bool(viewer.reports)
    return {
        "areas": area_rows, "skills": out_skills,
        "visibility": "names" if viewer.unrestricted or viewer.leader
                      else "your reports" if viewer.reports else "counts",
        "grid_names": grid_names,
        "note": "Evidence from recorded work, not a performance measure. No scores or rankings are kept.",
    }
