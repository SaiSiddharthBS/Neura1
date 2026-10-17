"""Knowledge health: the company's living documents, checked against what the graph knows today.

Handbooks, procedures, guides and documents written in Neura1 are meant to stay true; meeting notes, reports and
contracts are records of their date and are not checked. Each sentence of a living document is checked by rules, no
model:
  * it proposes a part the company rejected, calls an unapproved part approved, uses an expired quote, treats an
    obsolete or draft revision as current, or states a price that matches no current quote or notice (the same rules as
    the document fact checker and "never the same mistake twice");
  * it states a lead time that the newest record (a supplier notice, a quote, or recent orders) contradicts;
  * it routes work to someone who will be away soon (shown only to people allowed to see that leave);
  * it was last reviewed before something it mentions changed (a supplier notice or a decision).
Each finding quotes the exact sentence, and the page's owner can be asked to update it.
"""

import re
from datetime import date, timedelta

from falkordb import Graph

from neura1 import documents, guard, supply
from neura1.access import Viewer
from neura1.graph import rows
from neura1.ingest import extract
from neura1.ingest.unstructured import entity_lexicon, mentions

LIVING = """
MATCH (s:Source) WHERE s.kind IN ['doc', 'document']
RETURN s.id AS id, s.title AS title, s.kind AS kind, s.ref AS ref
"""
DATED = re.compile(r"(weekly|review_|kickoff|minutes|meeting|standup|ops_review|contract|report|TR-\d)", re.I)
OWNER = re.compile(r"\b(?:Owner|Maintained by|Prepared by|Author)\s*:?\s*([A-Z][a-z]+)")
REVIEWED = re.compile(r"\bLast reviewed\s*:\s*(\d{4}-\d{2}-\d{2})", re.I)
WEEKS = re.compile(r"\b(\d{1,2})\s*(?:-\s*)?weeks?\b", re.I)
ROUTE = re.compile(r"\b(go(?:es)? to|ask|contact|belongs? to|covers?|owned by|questions? (?:about|on))\b", re.I)

CHANGED_AFTER = """
MATCH (i:Item {id:$id})
OPTIONAL MATCH (d:Decision)-[:ABOUT]->(i) WHERE d.decided_at > $since
RETURN collect(DISTINCT {id: d.id, at: d.decided_at, summary: d.summary}) AS decisions
"""

AWAY_SOON = """
MATCH (p:Person)-[:HAS_ABSENCE]->(a:Absence) WHERE a.end_date >= $today AND a.start_date <= $until
OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p)
RETURN p.id AS id, p.name AS name, a.start_date AS start, a.end_date AS end, b.name AS backup
"""


def living_sources(graph: Graph) -> list[dict]:
    return [s for s in rows(graph, LIVING) if not DATED.search(s["id"]) and not DATED.search(s["title"] or "")]


def _lines(text: str) -> list[str]:
    """A bullet or line is the unit a reader takes as one statement ("NB54360 comes from Deccan. Lead time is 6
    weeks." is one statement about NB54360)."""
    return [x.strip() for x in text.split("\n") if x.strip()]


def check_source(graph: Graph, src: dict, today: date, facts: dict, notes: dict, away: dict, people: dict) -> dict:
    passages = extract.source_passages(graph, src["id"])
    head = " ".join(p["text"] for p in passages[:3])
    owner = (OWNER.search(head) or [None, None])[1]
    reviewed = (REVIEWED.search(head) or [None, None])[1]
    lexicon = entity_lexicon(graph)
    findings: list[dict] = []

    def add(kind, severity, title, message, passage, quote, record=None, evidence=None, person=None):
        if quote and quote in passage["text"]:
            line = next((x.strip() for x in passage["text"].split("\n") if quote in x), passage["text"])
            findings.append({"kind": kind, "severity": severity, "title": title, "message": message,
                             "passage": passage["id"], "quote": quote, "line": line, "record": record,
                             "evidence": evidence or [], "person": person})

    blocks, owner_of = [], {}
    for p in passages:
        for n, line in enumerate(_lines(p["text"])):
            blocks.append({"id": f"{p['id']}|{n}", "text": line})
            owner_of[f"{p['id']}|{n}"] = p
    flagged = documents.check(graph, blocks, Viewer(), adopt=guard.CHAT_ADOPT, facts=facts)
    expired_lines = {f["block_id"] for f in flagged if f["title"].endswith("has expired")}
    for f in flagged:
        if f["severity"] == "info":
            continue  # unknown ids and leave are handled below, more precisely
        if f["title"].startswith("Price for") and f["block_id"] in expired_lines:
            continue  # the expired quote is the real problem on that line
        add("contradicts", "high" if f["severity"] == "error" else "medium", f["title"], f["message"],
            owner_of[f["block_id"]], f["quote"], f["record"], f.get("sources"))

    for p in passages:
        for sentence in _lines(p["text"]):
            named = mentions(sentence, lexicon)
            weeks = WEEKS.search(sentence)
            if weeks:
                for item in [n for n in named if n in notes or n in facts["quoted_items"]]:
                    lead = supply.lead_time(graph, item, today, notes.get(item))
                    if lead["weeks"] is not None and int(weeks.group(1)) != lead["weeks"]:
                        newest = (f"the supplier notice of {notes[item]['received']}" if lead["basis"] == "notice"
                                  else f"quote {lead['source']}" if lead["basis"] == "quote" else "recent orders")
                        add("lead_time", "high", f"Lead time for {item} is out of date",
                            f"This says {weeks.group(1)} weeks; {newest} says {lead['weeks']} weeks.", p,
                            weeks.group(0), lead["source"])
            if ROUTE.search(sentence):
                for pid in [n for n in named if n in away]:
                    a = away[pid]
                    name = people.get(pid, pid)
                    add("away", "medium", f"Routes work to {name}, who is away soon",
                        f"{name} is away {a['start']} to {a['end']}. Backup: {a['backup'] or 'none recorded'}.",
                        p, name, pid, person=pid)
            if reviewed:
                for item in [n for n in named if n in notes]:
                    n = notes[item]
                    if (n.get("received") or "") > reviewed:
                        add("superseded", "medium", f"{item} changed after this page was last reviewed",
                            f"Reviewed {reviewed}; a supplier notice arrived {n['received']}"
                            + (f" (lead time {n['lead_weeks']} weeks" if n.get("lead_weeks") else "")
                            + (f", price from {n['effective_date']})" if n.get("new_unit_price") else ")" if n.get("lead_weeks") else "")
                            + ".", p, item, n["source"])
                for item in [n for n in named if n in facts["item_ids"]]:
                    changed = rows(graph, CHANGED_AFTER, {"id": item, "since": reviewed})
                    for d in [d for d in (changed[0]["decisions"] if changed else []) if d.get("id")]:
                        add("superseded", "medium", f"{item} has a newer decision ({d['id']})",
                            f"Decided {d['at']}, after this page was last reviewed ({reviewed}): {d['summary']}.",
                            p, item, d["id"])

    seen, unique = set(), []
    for f in findings:
        key = (f["passage"], f["quote"], f["kind"], f["title"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    order = {"high": 0, "medium": 1, "low": 2}
    unique.sort(key=lambda f: (order[f["severity"]], f["passage"]))
    return {"id": src["id"], "title": src["title"], "kind": src["kind"], "owner": owner,
            "owner_id": next((k for k, v in people.items() if v == owner), None), "reviewed": reviewed,
            "findings": unique, "passages": len(passages)}


def sweep(graph: Graph, viewer: Viewer, today: date | None = None) -> dict:
    """Every living document, healthiest last. Leave-based findings only for viewers who may see that leave."""
    today = today or date.today()
    facts = documents._facts(graph)
    facts["item_ids"] = {r["id"] for r in rows(graph, "MATCH (i:Item) RETURN i.id AS id")}
    facts["quoted_items"] = {r["id"] for r in rows(graph, "MATCH (:Quote)-[:FOR]->(i:Item) RETURN DISTINCT i.id AS id")}
    notes = supply.notices(graph)
    away = {}
    for a in rows(graph, AWAY_SOON, {"today": today.isoformat(), "until": (today + timedelta(days=45)).isoformat()}):
        away.setdefault(a["id"], a)
    people = {r["id"]: r["name"] for r in rows(graph, "MATCH (p:Person) RETURN p.id AS id, p.name AS name")}
    docs = []
    for src in living_sources(graph):
        d = check_source(graph, src, today, facts, notes, away, people)
        d["findings"] = [f for f in d["findings"] if f["kind"] != "away" or viewer.sees_leave_of(f["person"])]
        docs.append(d)
    docs.sort(key=lambda d: (-sum(f["severity"] == "high" for f in d["findings"]), -len(d["findings"]), d["title"] or ""))
    total = sum(len(d["findings"]) for d in docs)
    healthy = sum(1 for d in docs if not d["findings"])
    return {"documents": docs, "findings": total, "healthy": healthy, "checked": len(docs), "today": today.isoformat()}


def request_review(graph: Graph, source_id: str, viewer: Viewer) -> dict:
    """Ask the page's owner to update it: one task, listing what is out of date."""
    from neura1 import actions
    report = sweep(graph, viewer)
    doc = next((d for d in report["documents"] if d["id"] == source_id), None)
    if not doc:
        raise ValueError("Not a living document")
    if not doc["findings"]:
        raise ValueError("Nothing on this page is out of date")
    why = "; ".join(f"{f['title']}: “{f['quote']}”" for f in doc["findings"][:6])
    return actions.create_task(graph, f"Update “{doc['title']}”: {len(doc['findings'])} out-of-date "
                                      f"fact{'s' if len(doc['findings']) > 1 else ''}",
                               doc["owner"], source_id, why, viewer.name or "Neura1")
