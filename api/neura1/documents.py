"""Neura1 Docs: Word documents written with the company brain and checked against it.

- A document is kept as the exact .docx the editor produced, plus a plain-text projection that is ingested like any
  other source: passages linked to the parts, people, orders and projects they name. Saved documents are knowledge.
- Templates are composed from graph facts by code, not by a model.
- Fact checks are rules over the graph, not a model, so they cannot invent a problem. Each flag names its source.
- AI edits come from the local model, are returned per paragraph, and are applied in the editor as tracked changes.
  Any number or identifier the model introduces that is in neither the document nor the graph is reported.
"""

import hashlib
import re
from datetime import date, datetime, timezone
from pathlib import Path

from falkordb import Graph

from neura1 import scenarios
from neura1.access import MONEY_TEXT, Viewer
from neura1.config import settings
from neura1.graph import rows
from neura1.ingest.unstructured import REV_PHRASE, entity_lexicon, load_sources, mentions

DOC_DIR = "documents"
MAX_AI_CHARS = 12000


def _dir() -> Path:
    d = settings.data_dir / DOC_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- storage ----------

def create(graph: Graph, title: str, kind: str, by: Viewer, about: str | None = None) -> str:
    doc_id = "DOC-" + hashlib.sha256(f"{title}|{by.id}|{_now()}".encode()).hexdigest()[:8]
    graph.query("""
        CREATE (d:Document {id:$id, title:$title, kind:$kind, created_at:$now, updated_at:$now, version:0,
                            created_by:$by, audience:$aud})
        WITH d OPTIONAL MATCH (p:Person {id:$pid})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (d)-[:CREATED_BY]->(p))
        WITH d OPTIONAL MATCH (x {id:$about}) WHERE NOT x:Document
        FOREACH (_ IN CASE WHEN x IS NULL THEN [] ELSE [1] END | CREATE (d)-[:ABOUT]->(x))
    """, {"id": doc_id, "title": title.strip()[:160] or "Untitled document", "kind": kind, "now": _now(),
          "by": by.name, "pid": by.id or "", "about": about or "",
          # A handover note states someone's leave, so it follows the leave rule for that person.
          "aud": f"leave:{about}" if kind == "handover" and about else "everyone"})
    return doc_id


def list_docs(graph: Graph, viewer: Viewer) -> list[dict]:
    docs = rows(graph, """
        MATCH (d:Document)
        OPTIONAL MATCH (d)-[:ABOUT]->(x)
        RETURN d.id AS id, d.title AS title, d.kind AS kind, d.created_by AS created_by, d.updated_at AS updated_at,
               d.updated_by AS updated_by, d.version AS version, d.audience AS audience, d.words AS words,
               x.id AS about ORDER BY d.updated_at DESC
    """)
    return [d for d in docs if may_open(d, viewer)]


def get(graph: Graph, doc_id: str) -> dict | None:
    found = rows(graph, """
        MATCH (d:Document {id:$id}) OPTIONAL MATCH (d)-[:ABOUT]->(x)
        RETURN d.id AS id, d.title AS title, d.kind AS kind, d.created_by AS created_by, d.updated_at AS updated_at,
               d.updated_by AS updated_by, d.version AS version, d.audience AS audience, d.words AS words,
               x.id AS about, labels(x)[0] AS about_label
    """, {"id": doc_id})
    return found[0] if found else None


def may_open(doc: dict, viewer: Viewer) -> bool:
    """A document that states amounts is open to people who may see money, like #leadership; a handover note to
    the people who may see that person's leave."""
    for rule in (doc.get("audience") or "everyone").split(","):
        if rule == "money" and not viewer.sees_money:
            return False
        if rule.startswith("leave:") and not viewer.sees_leave_of(rule[6:]):
            return False
    return True


def file_path(doc_id: str) -> Path:
    return _dir() / f"{doc_id}.docx"


def save(graph: Graph, doc_id: str, docx: bytes, title: str, blocks: list[str], by: Viewer) -> dict:
    """Keep the .docx and make its text company knowledge (re-saving updates the same passages in place)."""
    file_path(doc_id).write_bytes(docx)
    blocks = [b.strip() for b in blocks if b and b.strip()]
    if blocks and blocks[0] == title.strip():
        blocks = blocks[1:]  # the title is written once, as the heading
    text = "\n\n".join(blocks)
    current = rows(graph, "MATCH (d:Document {id:$id}) RETURN d.audience AS a", {"id": doc_id})
    rules = [r for r in ((current[0]["a"] if current else "") or "").split(",") if r.startswith("leave:")]
    rules += ["money"] if MONEY_TEXT.search(text) else []
    audience = ",".join(rules) or "everyone"
    source_id = f"{DOC_DIR}/{doc_id}.md"
    md = _dir() / f"{doc_id}.md"
    shared = not any(r.startswith("leave:") for r in rules)
    passages = {}
    if shared:
        # Shared documents become company knowledge; amounts in them stay hidden from people who may not see money.
        md.write_text(f"# {title}\n\nDate: {date.today().isoformat()}\n\n{text}\n", encoding="utf-8")
        passages = load_sources(graph, root=settings.data_dir, files=[md])
    graph.query("""
        MATCH (d:Document {id:$id})
        SET d.title=$title, d.updated_at=$now, d.updated_by=$by, d.version=coalesce(d.version, 0) + 1,
            d.words=$words, d.audience=$aud
        WITH d OPTIONAL MATCH (s:Source {id:$sid})
        FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END |
                 SET s.kind='document', s.title=$title, s.audience=$aud MERGE (d)-[:HAS_SOURCE]->(s))
    """, {"id": doc_id, "sid": source_id, "title": title, "now": _now(), "by": by.name,
          "words": len(text.split()), "aud": audience})
    linked = rows(graph, "MATCH (:Source {id:$sid})<-[:PART_OF]-(:Chunk)-[:MENTIONS]->(x) "
                         "RETURN DISTINCT x.id AS id ORDER BY id", {"sid": source_id})
    return {**(get(graph, doc_id) or {}), "id": doc_id, "passages": passages.get(source_id, 0),
            "linked": [r["id"] for r in linked] if shared else [], "audience": audience, "shared": shared}


# ---------- templates, composed from the graph ----------

def _table(head: list[str], body: list[list]) -> str:
    if not body:
        return "_None._"
    cell = lambda v: str(v if v not in (None, "") else "—").replace("|", "/").replace("\n", " ")
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                     + ["| " + " | ".join(cell(v) for v in r) + " |" for r in body])


def _money(v, viewer: Viewer) -> str:
    if not viewer.sees_money:
        return "(visible to leadership, BD and purchase)"
    try:
        return f"₹{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return "—"


def _footer() -> str:
    return f"_Prepared with Neura1 from Flyvi's company graph on {date.today().isoformat()}. Check before sending._"


def change_notice(graph: Graph, report: dict, viewer: Viewer) -> tuple[str, str]:
    part, change, cost = report["part"], report["change"], report.get("cost") or {}
    title = f"Engineering change notice: {part['id']} supply change"
    used = [[w["product"], w["revision"], w["status"], w["qty_per_unit"] if w["applicable"] else "not affected"]
            for w in report["where_used"]]
    builds = [[b["build"], b["revision"], b["planned_date"], b["parts_needed"], b["shortfall"],
               ", ".join(f"{o['order']} ({o['customer']})" for o in b["orders"]) or "—",
               "at risk" if b["at_risk"] else "covered"] for b in report["builds"]]
    alts = []
    for a in report.get("alternates", []):
        verdict = "; ".join(f"{d['id']}: {d['outcome']} on {d['decided_at']} by {d.get('decided_by') or '—'}"
                            for d in a.get("decisions", []) if d.get("outcome") == "rejected")
        alts.append([a["id"], a["name"], verdict or "not approved by engineering", a.get("note", "")])
    tasks = [[t["owner"], t["title"], t["why"]] for t in report.get("actions", [])]
    lead = f"{change['lead_weeks']} weeks" if change.get("lead_weeks") else "unchanged"
    price = (f"{_money(cost.get('baseline_unit_price'), viewer)} → {_money(change.get('new_unit_price'), viewer)}"
             if change.get("new_unit_price") else "unchanged")
    cost_lines = (f"Net purchase need: {cost.get('net_need', '—')} parts (gross {cost.get('gross_need', '—')}, "
                  f"free stock {cost.get('free_stock', '—')}). Total impact: **{_money(cost.get('total_delta'), viewer)}** "
                  f"({cost.get('formula', '—') if viewer.sees_money else 'formula hidden'}).") if cost else "_Not computed._"
    md = f"""# {title}

{_table(["Field", "Value"], [["Part", f"{part['id']}: {part['name']} ({part.get('manufacturer') or '—'})"],
                             ["Owner", part.get("owner")], ["Prepared by", viewer.name],
                             ["Date", date.today().isoformat()], ["Policy", "HB-ENG-04 Engineering change policy"]])}

## 1. Change

Supplier notice{f" ({change['source_id'].split('/')[-1]})" if change.get('source_id') else ''}: unit price {price}, lead time {lead}, effective {change.get('effective_date') or '—'}.

## 2. Affected products

{_table(["Product", "Revision", "Status", "Qty per unit"], used)}

## 3. Builds and customer orders at risk

{_table(["Build", "Revision", "Planned", "Parts needed", "Shortfall", "Orders", "Status"], builds)}

## 4. Cost impact

{cost_lines}

## 5. Alternates considered

{_table(["Part", "Description", "Engineering decision", "Note"], alts)}

## 6. Required reviews and actions

{_table(["Owner", "Action", "Why"], tasks)}

## 7. Approval

{_table(["Role", "Name", "Signature", "Date"], [["Prepared by", viewer.name, "", ""], ["R&D review", "Vishwas", "", ""],
                                                 ["Approved by (Chief Technology Officer)", "Hithesh", "", ""]])}

{_footer()}
"""
    return title, md


def customer_response(graph: Graph, customer_id: str, viewer: Viewer) -> tuple[str, str]:
    c = scenarios.customer_360(graph, customer_id)
    if c["status"] != "ok":
        raise KeyError(customer_id)
    cust = c["customer"]
    title = f"Response to {cust['name']}"
    orders = [[o["id"], o["revision"], o["qty"], o["due"], o.get("build") or "—"] for o in c["orders"]]
    plan = [[a["owner"], a["title"]] for a in c.get("actions", [])]
    md = f"""# {title}

Date: {date.today().isoformat()}

To: {cust['name']}

From: {cust.get('account_manager') or viewer.name}, Flyvi Technologies Pvt. Ltd.

Subject: Your open orders with Flyvi and our plan

Dear {cust['name']} team,

Thank you for raising this with us. We have reviewed it across engineering, production and support, and this letter sets out where your orders stand and what we are doing.

## Your open orders

{_table(["Order", "Product revision", "Quantity", "Due", "Build"], orders)}

## What we are doing

{_table(["Owner at Flyvi", "Action"], plan)}

We will confirm dates for each action in writing and keep you updated until this is closed.

Yours sincerely,

{cust.get('account_manager') or viewer.name}

Flyvi Technologies Pvt. Ltd.

{_footer()}
"""
    return title, md


def handover_note(graph: Graph, person_id: str, viewer: Viewer) -> tuple[str, str]:
    a = scenarios.absence_impact(graph, person_id)
    if a["status"] != "ok":
        raise KeyError(person_id)
    p = a["person"]
    if not viewer.sees_leave_of(person_id):
        raise PermissionError("Leave details are visible to the person, their management chain, backup, HR and leadership")
    title = f"Handover note: {p['name']}"
    period = f"{a['absence']['start']} to {a['absence']['end']}" if a.get("absence") else "dates to be confirmed"
    tasks = [[t["title"], t["status"], next((x["owner"] for x in a["actions"] if x.get("target") == t["id"]), p.get("backup"))]
             for t in a["open_tasks"]]
    owned = [[o["id"], o["name"], ", ".join(o.get("open_tasks_on_it") or []) or "—"] for o in a["owned"]]
    know = [[k["id"], f"{round(k['share'] * 100)}%", k.get("next_best") or "—"] for k in a["knowledge_at_risk"]]
    md = f"""# {title}

{_table(["Field", "Value"], [["Away", period], ["Backup", p.get("backup")], ["Manager", p.get("manager")],
                             ["Prepared by", viewer.name], ["Policy", "HB-HR-02 Leave and handover"]])}

## Open work and who takes it

{_table(["Task", "Status", "Covered by"], tasks)}

## What {p['name']} owns

{_table(["Record", "Name", "Open work on it"], owned)}

## Knowledge the company relies on {p['name']} for

{_table(["Subject", "Share of company knowledge", "Next best person"], know)}

## Notes for the backup

Add anything not in the records above: context, contacts, and where files live.

{_footer()}
"""
    return title, md


# ---------- inserting live facts ----------

def insert_block(graph: Graph, kind: str, record: str, viewer: Viewer) -> str:
    if kind == "where_used":
        from neura1 import queries as Q
        r = rows(graph, Q.WHERE_USED, {"item_id": record})
        return f"**Where {record} is used**\n\n" + _table(
            ["Product", "Revision", "Status", "Qty per unit"],
            [[x["product"], x["revision"], x["status"], x["qty_per_unit"] if x["applicable"] else "not affected"] for x in r])
    if kind == "decisions":
        r = rows(graph, """
            MATCH (d:Decision)-[:ABOUT|INSTEAD_OF]->(x {id:$id}) OPTIONAL MATCH (d)-[:DECIDED_BY]->(p:Person)
            RETURN DISTINCT d.id AS id, d.outcome AS outcome, d.summary AS summary, d.reason AS reason,
                   d.decided_at AS at, p.name AS by ORDER BY at
        """, {"id": record})
        return f"**Decisions about {record}**\n\n" + _table(["Decision", "Outcome", "Summary", "Reason", "Date", "By"],
                                                           [[x["id"], x["outcome"], x["summary"], x["reason"], x["at"], x["by"]] for x in r])
    if kind == "owners":
        from neura1 import brain
        w = brain.who_knows(graph, record)
        return f"**Who knows about {record}**\n\n" + _table(
            ["Person", "Role", "Team", "Why"],
            [[p["name"], p.get("role"), p.get("team"), ", ".join(sorted({s["signal"] for s in p["signals"]}))]
             for p in w.get("people", [])[:6]])
    if kind == "orders":
        c = scenarios.customer_360(graph, record)
        if c["status"] != "ok":
            raise KeyError(record)
        return f"**Open orders for {c['customer']['name']}**\n\n" + _table(
            ["Order", "Revision", "Qty", "Due", "Value"],
            [[o["id"], o["revision"], o["qty"], o["due"], _money(o.get("value"), viewer)] for o in c["orders"]])
    if kind == "history":
        from neura1 import explore
        ev = [e for e in explore.timeline(graph, record) if e["kind"] != "leave" or viewer.sees_leave_of(record)][:10]
        return f"**Recent history of {record}**\n\n" + _table(
            ["Date", "What", "Detail"], [[e["at"][:10], e["title"], (e["detail"] or "")[:140]] for e in ev])
    raise ValueError(f"Unknown insert kind {kind}")


# ---------- fact check: rules over the graph ----------

ADOPT = re.compile(r"\b(switch\w*|replac\w*|substitut\w*|adopt\w*|use|using|move to|go with|"
                   r"approved|qualified|cost[- ]down)\b", re.I)
NEGATION = re.compile(r"\b(not|never|reject\w*|do not|don't|avoid|instead of keeping)\b", re.I)
APPROVED_WORDS = re.compile(r"\b(approved|qualified|released for production)\b", re.I)
ASSIGN = re.compile(r"\b(will|to review|owner|assign\w*|responsible|lead|by)\b", re.I)
SENTENCE = re.compile(r"(?<=[.!?;])\s+")
ID_LIKE = re.compile(r"(?<![\w-])([A-Z]{1,4})-?(\d{2,6})(?:-[A-Z0-9]{1,3})?(?![\w-])")


def _facts(graph: Graph) -> dict:
    today = date.today().isoformat()
    return {
        "rejected": rows(graph, """
            MATCH (d:Decision {outcome:'rejected'})-[:ABOUT]->(alt:Item)
            WHERE coalesce(d.status, 'active') = 'active'
            OPTIONAL MATCH (d)-[:INSTEAD_OF]->(inc:Item) OPTIONAL MATCH (d)-[:DECIDED_BY]->(p:Person)
            OPTIONAL MATCH (d)-[:EVIDENCED_BY]->(c:Chunk)
            RETURN d.id AS id, alt.id AS item, inc.id AS instead_of, d.summary AS summary, d.reason AS reason,
                   d.decided_at AS at, p.name AS by, collect(c.id)[0..3] AS sources"""),
        "approved": {r["id"] for r in rows(graph, "MATCH (d:Decision {outcome:'approved'})-[:ABOUT]->(i:Item) RETURN i.id AS id")},
        "alternates": rows(graph, "MATCH (a:Item)-[r:ALTERNATE_OF]->(b:Item) RETURN a.id AS id, b.id AS of, r.note AS note"),
        "quotes": rows(graph, "MATCH (q:Quote)-[:FOR]->(i:Item) OPTIONAL MATCH (s:Supplier)-[:QUOTED]->(q) "
                              "RETURN q.id AS id, i.id AS item, q.unit_price AS price, q.valid_until AS until, "
                              "q.lead_weeks AS lead, s.name AS supplier"),
        "revisions": rows(graph, "MATCH (r:Revision) RETURN r.id AS id, r.status AS status"),
        "away": rows(graph, "MATCH (p:Person)-[:HAS_ABSENCE]->(a:Absence) WHERE a.end_date >= $today "
                            "OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p) "
                            "RETURN p.id AS id, p.name AS name, a.start_date AS start, a.end_date AS end, b.name AS backup",
                     {"today": today}),
        "notice_prices": rows(graph, "MATCH (s:Source)<-[:PART_OF]-(c:Chunk)-[:MENTIONS]->(i:Item) "
                                     "WHERE s.kind IN ['notice', 'chat', 'ticket'] RETURN i.id AS item, c.text AS text"),
        "ids": {r["id"] for r in rows(graph, "MATCH (n) WHERE n.id IS NOT NULL AND NOT n:Chunk AND NOT n:Turn "
                                             "AND NOT n:Event AND NOT n:Message RETURN n.id AS id")},
        "today": today,
    }


def _amounts(text: str) -> list[tuple[str, float]]:
    """Rupee amounts written in text, e.g. "₹320" or "INR 1,250.50"; lakh and crore figures are skipped."""
    out = []
    for m in MONEY_TEXT.finditer(text):
        if m.group(3):
            continue
        digits = m.group(0)[len(m.group(1)):].replace(",", "").strip()
        try:
            out.append((m.group(0).strip(), float(digits)))
        except ValueError:
            pass
    return out


def check(graph: Graph, blocks: list[dict], viewer: Viewer) -> list[dict]:
    """Return flags: {block_id, quote, severity, title, message, record, sources}. `quote` is an exact substring."""
    f = _facts(graph)
    lexicon = entity_lexicon(graph)
    known_prefixes = {m.group(1) for i in f["ids"] for m in [ID_LIKE.fullmatch(i)] if m}
    flags = []

    def flag(block, quote, severity, title, message, record=None, sources=None):
        if quote and quote in block["text"]:
            flags.append({"block_id": block["id"], "quote": quote, "severity": severity, "title": title,
                          "message": message, "record": record, "sources": sources or []})

    for b in blocks:
        text = b.get("text") or ""
        if not text.strip():
            continue
        named = mentions(text, lexicon) | {f"{i}-{r}" for i, r in REV_PHRASE.findall(text)}
        # Claims are judged per sentence, so "MX-3360 is approved" does not make a claim about another part.
        sentences = [x for x in SENTENCE.split(text) if x.strip()]

        def claims(item_id: str, pattern: re.Pattern) -> bool:
            return any(item_id in sentence_ids(x) and pattern.search(x) and not NEGATION.search(x) for x in sentences)

        def sentence_ids(x: str) -> set[str]:
            return mentions(x, lexicon) | {f"{i}-{r}" for i, r in REV_PHRASE.findall(x)}

        rejected_here = set()
        for d in f["rejected"]:
            if d["item"] in named and d["id"] not in text and claims(d["item"], ADOPT):
                rejected_here.add(d["item"])
                flag(b, d["item"], "error", f"{d['item']} was rejected ({d['id']})",
                     f"{d['summary']}. Reason: {d['reason']}. Decided by {d['by'] or 'engineering'} on {d['at']}. "
                     f"Reopen the decision before proposing it again.", d["id"], d["sources"])
        for a in f["alternates"]:
            if a["id"] in named and a["id"] not in f["approved"] and a["id"] not in rejected_here \
                    and claims(a["id"], APPROVED_WORDS):
                flag(b, a["id"], "error", f"{a['id']} is not approved",
                     f"{a['id']} is only a suggested alternate for {a['of']} ({a['note']}). No engineering approval "
                     f"exists in the graph.", a["id"])
        for q in f["quotes"]:
            if q["id"] in text and q["until"] and q["until"] < f["today"]:
                flag(b, q["id"], "warning", f"{q['id']} has expired",
                     f"Quote {q['id']} from {q['supplier'] or 'the supplier'} for {q['item']} was valid until "
                     f"{q['until']}. Use a current quote.", q["id"])
        for r in f["revisions"]:
            # A table cell holding only the id, or a sentence that already says obsolete/draft, is not a claim.
            if r["id"] in named and r["status"] in ("obsolete", "draft") and len(text.strip()) > len(r["id"]) + 3 \
                    and r["status"] not in text.lower():
                shown = next((m.group(0) for m in REV_PHRASE.finditer(text)
                              if f"{m.group(1)}-{m.group(2)}" == r["id"]), r["id"])
                flag(b, shown, "warning", f"{r['id']} is {r['status']}",
                     f"Revision {r['id']} is {r['status']}, not released. Check which revision is meant.", r["id"])
        if viewer.sees_money:
            for item in {q["item"] for q in f["quotes"]} & named:
                allowed = {float(q["price"]) for q in f["quotes"] if q["item"] == item and q["price"]
                           and (not q["until"] or q["until"] >= f["today"])}
                allowed |= {v for n in f["notice_prices"] if n["item"] == item for _, v in _amounts(n["text"])}
                for shown, value in _amounts(text):
                    if allowed and value not in allowed and value < 100000:
                        current = ", ".join(f"₹{float(q['price']):g} ({q['id']}, {q['supplier'] or '—'}, valid to {q['until']})"
                                            for q in f["quotes"] if q["item"] == item and q["price"]
                                            and (not q["until"] or q["until"] >= f["today"]))
                        flag(b, shown, "warning", f"Price for {item} does not match the records",
                             f"Current quotes for {item}: {current or 'none'}. Supplier notices on file mention "
                             f"other amounts; none is {shown}.", item)
        for p in f["away"]:
            if p["id"] in named and claims(p["id"], ASSIGN) and viewer.sees_leave_of(p["id"]):
                flag(b, p["name"], "info", f"{p['name']} is away {p['start']} to {p['end']}",
                     f"Planned leave from {p['start']} to {p['end']}. Backup: {p['backup'] or 'not set'}.", p["id"])
        for m in ID_LIKE.finditer(text):
            token = m.group(0)
            if m.group(1) in known_prefixes and token not in f["ids"] and token not in named \
                    and not any(token.startswith(i + "-") or i.startswith(token) for i in named):
                flag(b, token, "info", f"{token} is not in the records",
                     f"No part, order, build, quote or decision called {token} exists in Flyvi's graph. Check for a typo.")
    seen, out = set(), []
    for x in flags:
        key = (x["block_id"], x["quote"], x["title"])
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


# ---------- AI edits ----------

EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "text": {"type": "string"}}, "required": ["id", "text"]}},
        "note": {"type": "string"},
    },
    "required": ["edits", "note"],
}

EDIT_SYSTEM = """You edit documents for Flyvi Technologies, an Indian maker of power and control electronics.
You receive numbered paragraphs and an instruction. Return JSON {"edits": [{"id", "text"}], "note"}:
- Include only paragraphs that must change, each with its complete new text. Leave others out.
- To remove a paragraph, return it with empty text.
- Keep every fact, number, date, name and part number unless the instruction asks to change it.
- Never invent numbers, dates, names, orders or part numbers. Use only the document and COMPANY FACTS.
- If COMPANY FACTS contradict the document, follow the instruction but mention the conflict in "note".
- Keep the language plain and professional. Do not add markdown symbols.
- Never add titles or honorifics (Mr., Ms., Sir, Madam) to names, and never assume anyone's gender.
- Keep the capitalisation of words you do not change.
- "note" is one short sentence to the user about what you changed."""


def _ground(graph: Graph, text: str, viewer: Viewer) -> list[str]:
    """Short, checkable facts about the records the text names, for the model to stay consistent with."""
    named = sorted(mentions(text, entity_lexicon(graph)))[:12]
    if not named:
        return []
    facts = []
    for r in rows(graph, """
        MATCH (x) WHERE x.id IN $ids
        OPTIONAL MATCH (o:Person)-[:OWNS]->(x)
        RETURN x.id AS id, labels(x)[0] AS label, coalesce(x.name, x.title, x.summary, '') AS name,
               x.status AS status, x.role AS role, o.name AS owner
    """, {"ids": named}):
        bits = [f"{r['id']} ({r['label']})", r["name"]]
        bits += [f"status {r['status']}"] if r["status"] else []
        bits += [f"role {r['role']}"] if r["role"] else []
        bits += [f"owner {r['owner']}"] if r["owner"] else []
        facts.append(", ".join(b for b in bits if b))
    for d in rows(graph, "MATCH (d:Decision)-[:ABOUT]->(x) WHERE x.id IN $ids RETURN d.id AS id, d.outcome AS o, "
                         "d.summary AS s, d.reason AS r, d.decided_at AS at", {"ids": named}):
        facts.append(f"Decision {d['id']} ({d['o']}, {d['at']}): {d['s']}. {d['r'] or ''}")
    if viewer.sees_money:
        for q in rows(graph, "MATCH (q:Quote)-[:FOR]->(i:Item) WHERE i.id IN $ids AND q.valid_until >= $t "
                             "RETURN q.id AS id, i.id AS item, q.unit_price AS p, q.lead_weeks AS lw",
                      {"ids": named, "t": date.today().isoformat()}):
            facts.append(f"Quote {q['id']} for {q['item']}: ₹{q['p']} per unit, {q['lw']} weeks lead time")
    return facts


TOKEN = re.compile(r"(?<![\w.])(?:[A-Z]{1,5}-?\d[\w-]*|\d[\d,]*(?:\.\d+)?)(?![\w])")


def invented(original: str, facts: list[str], new: str) -> list[str]:
    """Numbers and identifiers in the model's text that appear in neither the document nor the facts."""
    known = original + "\n" + "\n".join(facts)
    norm = lambda s: s.replace(",", "")
    known_n = norm(known)
    return sorted({t for t in TOKEN.findall(new) if norm(t) not in known_n and len(t) > 1})


def ai_edit(graph: Graph, instruction: str, blocks: list[dict], viewer: Viewer, title: str = "") -> dict:
    from neura1.llm import chat_json

    blocks = [b for b in blocks if b.get("id")]
    body = "\n".join(f"[{b['id']}] {b.get('text') or ''}" for b in blocks)
    if len(body) > MAX_AI_CHARS:
        raise ValueError("That is too much text for one edit on this machine. Select a section and try again.")
    facts = _ground(graph, body + "\n" + instruction, viewer)
    user = (f"DOCUMENT: {title}\n\nPARAGRAPHS:\n{body}\n\nCOMPANY FACTS:\n"
            + ("\n".join(f"- {x}" for x in facts) or "- none") + f"\n\nINSTRUCTION: {instruction}")
    out = chat_json(EDIT_SYSTEM, user, EDIT_SCHEMA, "document_edits")
    by_id = {b["id"]: b.get("text") or "" for b in blocks}
    edits, warnings = [], []
    for e in out.get("edits", []):
        # Models sometimes echo the id with its brackets; with one paragraph there is only one it can mean.
        eid = str(e.get("id") or "").strip().strip("[]").strip()
        if eid not in by_id and len(by_id) == 1:
            eid = next(iter(by_id))
        if eid not in by_id:
            continue
        text = re.sub(r"^\s*(#+|\*\*|- )\s*", "", (e.get("text") or "").strip())
        text = re.sub(r"^\[[^\]]{1,40}\]\s*", "", text)
        if text == by_id[eid].strip():
            continue
        made_up = invented(body, facts, text)
        if made_up:
            warnings.append(f"Check the edited text: {', '.join(made_up)} is not in the document or the records.")
        edits.append({"id": eid, "text": text, "before": by_id[eid]})
    return {"edits": edits, "note": out.get("note") or "", "warnings": warnings, "facts": facts}


def import_text(filename: str, data: bytes) -> tuple[str, str]:
    """Turn an uploaded PDF, Markdown or text file into Markdown the editor can open."""
    import tempfile

    stem = Path(filename).stem.replace("_", " ")
    if filename.lower().endswith(".pdf"):
        from neura1.ingest.unstructured import _pdf

        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(data)
            tmp.flush()
            segs = _pdf(Path(tmp.name))
        return stem, f"# {stem}\n\n" + "\n\n".join(s.text for s in segs)
    text = data.decode("utf-8", errors="replace")
    return stem, text if text.lstrip().startswith("#") else f"# {stem}\n\n{text}"

