"""Ask the company brain: a tool-calling loop over bounded graph tools.

The model never sees the database directly. It chooses among named, parameterised tools and
one guarded read-only Cypher tool. Every tool call and its Cypher is returned with the answer.
"""

import json
import re
from datetime import date
from decimal import Decimal

from falkordb import Graph

from neura1 import brain, queries as Q, scenarios
from neura1.config import settings
from neura1.graph import rows
from neura1.impact import ChangeEvent, Trace, analyse
from neura1.llm import client

SYSTEM = """You are Neura1, the company brain of Flyvi Technologies, a Bengaluru company (part of Datasol (Bangalore)
Limited) that designs and builds power distribution units, power converters, battery chargers and embedded control
systems for aerospace and defence. The data you see is a synthetic demo of that company.
Answer questions using ONLY the results of your tools. Rules:
- Call tools to look things up; never answer from memory or assumptions.
- Cite the ids you relied on (part numbers, revisions, orders, decisions like DEC-117, documents like TR-112).
- If the tools return nothing relevant, say plainly that it is not recorded. Do not guess.
- A part listed as an alternate is NOT approved unless its "approval" field says APPROVED. A passed bench test
  or a chat message is not an approval. Use the alternates tool and repeat its approval wording.
- Use ids exactly as the tools return them (e.g. NB54360, PDU-28-C).
- Quantities and costs must come from tool results, not your own arithmetic, unless you show the formula.
- Be concise: a short direct answer, then the supporting facts."""

WRITE = re.compile(r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|LOAD|CALL\s+db\.idx\.\w+\.(create|drop))\b", re.I)


APPROVAL_TEXT = {
    "approved": "APPROVED for use by a recorded decision",
    "rejected": "REJECTED: must not be used (see decisions)",
    "pending_review": "NOT APPROVED: candidate pending engineering review; only test or bench evidence so far",
    "unqualified": "NOT APPROVED: listed by cross-reference only, no qualification evidence",
}


def check_approval_claims(graph: Graph, answer: str) -> list[str]:
    """Deterministic safety net: flag any sentence that calls a part approved when the graph says it is not."""
    from neura1.impact import alternate_status

    warnings = []
    statuses = {}
    # Only the alternates themselves (the part the alternate stands in for is the approved incumbent).
    for r in rows(graph, "MATCH (a:Item)-[:ALTERNATE_OF]->(:Item) RETURN DISTINCT a.id AS id"):
        decisions = rows(graph, """MATCH (d:Decision)-[:ABOUT]->(:Item {id:$id})
                                   RETURN d.outcome AS outcome, d.authority AS authority, d.status AS status""",
                         {"id": r["id"]})
        statuses[r["id"]] = alternate_status(decisions)
    for sentence in re.split(r"(?<=[.!?])\s+", answer):
        if not re.search(r"\bapproved\b", sentence, re.I) or re.search(r"\b(not|un)\s*-?approved\b", sentence, re.I):
            continue
        for part, status in statuses.items():
            if part in sentence and status != "approved":
                warnings.append(f"Check this: the graph says {part} is {APPROVAL_TEXT[status]}.")
    return warnings


def guard_cypher(q: str) -> str:
    if WRITE.search(q):
        raise ValueError("Only read queries are allowed")
    if not re.search(r"\bLIMIT\s+\d+\s*$", q.strip(), re.I):
        q = q.rstrip().rstrip(";") + " LIMIT 50"
    return q


TOOLS = [
    ("resolve_item", "Find an item (product, assembly, part, firmware, test) or a revision ('PDU-28 Rev C' is PDU-28-C) "
                     "by id or manufacturer part number.",
     {"text": {"type": "string"}}),
    ("where_used", "Which product revisions use an item or an assembly (and which revision of the assembly), quantity "
                   "per unit, and whether each revision is released.",
     {"item_id": {"type": "string"}}),
    ("change_impact", "Full impact of a price and/or lead-time change on a part: builds, orders, customers, "
                      "dependencies, alternates with decisions, cost scenario and required tasks.",
     {"item_id": {"type": "string"}, "new_unit_price": {"type": ["number", "null"]},
      "lead_weeks": {"type": ["integer", "null"]}}),
    ("dependents", "Firmware modules, test procedures and other items that depend on a part, with their owners.",
     {"item_id": {"type": "string"}}),
    ("exposure", "Planned builds (with planner), customer orders (due dates, penalty notes), customers and account "
                 "managers, and units already shipped to the field. Pass a part, a product (e.g. PDU-28) or a revision "
                 "(e.g. PDU-28-C).",
     {"item_id": {"type": "string"}}),
    ("decisions", "Recorded decisions about an item or its alternates, with who decided and verbatim evidence.",
     {"item_id": {"type": "string"}}),
    ("alternates", "Alternate parts listed for a part, with their quotes and approval status.",
     {"item_id": {"type": "string"}}),
    ("quotes", "Supplier quotes with price, lead time and validity dates. Pass an item id, or leave it empty for "
               "every quote.", {"item_id": {"type": ["string", "null"]}}),
    ("organisation", "Flyvi's leadership and their titles (Managing Director, directors, COO, CTO, General Manager), "
                     "and, given a person's name, their manager, direct reports, team and backup.",
     {"name": {"type": ["string", "null"]}}),
    ("notices", "Supplier notices received (price, lead-time, end-of-life changes), with their full text.", {}),
    ("who_knows", "Who knows about something: a part, project, customer, order or alias like 'pmic_seq.c'. "
                  "Returns people ranked with the reasons (owns it, decided, discussed, works on it).",
     {"text": {"type": "string"}}),
    ("person", "A person's profile: role, team, manager, backup, what they own, projects, decisions, open tasks, "
               "recently finished work, topics.",
     {"name": {"type": "string"}}),
    ("project", "A project's lead, members, scope, related decisions, open tasks and recent discussion. "
                "Pass the project name or id; use list_projects first if unsure.",
     {"text": {"type": "string"}}),
    ("list_projects", "All projects with status, lead and target date.", {}),
    ("recent_changes", "What changed recently across the company, and knowledge that may be out of date "
                       "(edited evidence, decisions on obsolete revisions, expiring quotes).", {}),
    ("absence_impact", "What happens if a person is away: what they own, open tasks, projects they lead, knowledge "
                       "only they hold, conflicts, and the handover plan. Pass the person's name.",
     {"name": {"type": "string"}}),
    ("customer", "Everything about a customer: orders and their value, penalties, field units, tickets and "
                 "escalations, projects, who knows them, and the escalation plan. Pass the customer name or id.",
     {"text": {"type": "string"}}),
    ("risk_radar", "Where the company is fragile: graph chokepoints (betweenness), single-sourced parts with order "
                   "value at risk, knowledge held by one person, customer concentration, workload, and how teams "
                   "actually cluster (community detection).", {}),
    ("recall", "What has already been asked and answered about a record or topic, by anyone (shared memory of past "
               "conversations). Use for 'did we discuss', 'what did we decide earlier', or before re-investigating.",
     {"text": {"type": "string"}}),
    ("propose_task", "Draft a task for a person. It is NOT created until a human confirms it. Use when the user "
                     "asks to assign, follow up, or get something done.",
     {"owner": {"type": "string"}, "title": {"type": "string"}, "target": {"type": ["string", "null"]},
      "why": {"type": "string"}}),
    ("search_documents", "Search chats, tickets, reports and notices by meaning and keywords; also returns the records "
                         "the passages mention.", {"query": {"type": "string"}}),
    ("read_only_cypher", "Run a read-only Cypher query when no other tool fits. Relationships: (Item)-[:HAS_REV]->"
                         "(Revision)-[:CONTAINS {qty, refdes}]->(Item|Revision); (Build)-[:BUILDS]->(Revision); "
                         "(Customer)-[:PLACED]->(Order)-[:FULFILLED_BY]->(Build); (Supplier)-[:QUOTED]->(Quote)-[:FOR]->"
                         "(Item); (Person)-[:REPORTS_TO|BACKS_UP]->(Person); (Person)-[:MEMBER_OF]->(Team); (Person)-"
                         "[:OWNS]->(Item|Build|Customer); (Action)-[:ASSIGNED_TO]->(Person); (Chunk)-[:PART_OF]->(Source). "
                         "Quote properties: unit_price, currency, lead_weeks, valid_from, valid_until (ISO date strings). "
                         "Build: qty, planned_date. Revision: status. Names are on .name, ids on .id.",
     {"query": {"type": "string"}}),
]


def run_tool(graph: Graph, trace: Trace, name: str, args: dict):
    if name == "resolve_item":
        text = str(args.get("text", "")).strip()
        found = trace.run(name, Q.RESOLVE_ITEM, {"text": text})
        if found:
            return found
        # Revisions: "PDU-28 Rev C", "PDU-28C" or "PDU-28-C" all name the revision PDU-28-C.
        m = re.fullmatch(r"([A-Za-z]{2,4}-\d{2,3})[\s-]*(?:rev(?:ision)?\.?\s*)?([A-Za-z0-9])", text, re.I)
        rev_id = f"{m.group(1).upper()}-{m.group(2).upper()}" if m else text
        revs = trace.run("resolve_revision", """MATCH (i:Item)-[:HAS_REV]->(r:Revision) WHERE toUpper(r.id) = toUpper($t)
                                                 RETURN r.id AS id, 'revision' AS kind, i.id AS of_item, i.name AS name,
                                                        r.status AS status""", {"t": rev_id})
        if revs:
            return revs
        # Small models often pass several part numbers at once ("NB54360 NB54361-L"): resolve each one.
        out = []
        for token in [t for t in re.split(r"[\s,;/]+", text) if len(t) >= 3]:
            hit = trace.run(name, Q.RESOLVE_ITEM, {"text": token}) or \
                [s | {"suggestion": True} for s in trace.run("suggest_items", Q.SUGGEST_ITEMS, {"text": token})]
            out.extend(hit)
        return out or {"error": f"No item matches {text!r}", "hint": "pass one part number or id per call"}
    if name == "where_used":
        used = trace.run(name, Q.WHERE_USED, {"item_id": args["item_id"]})
        # Assemblies are built in as a specific revision (Revision CONTAINS Revision), not as the item itself.
        nested = trace.run("where_used_assembly", """
            MATCH (a:Item {id:$id})-[:HAS_REV]->(ar:Revision)
            MATCH path = (prod:Item)-[:HAS_REV]->(top:Revision)-[:CONTAINS*1..6]->(ar)
            WHERE NOT ()-[:CONTAINS]->(top)
            RETURN prod.id AS product, top.id AS revision, top.status AS status, ar.id AS contains_revision,
                   reduce(q = 1, r IN relationships(path) | q * coalesce(r.qty, 1)) AS qty_per_unit""", {"id": args["item_id"]})
        return {"uses": used, "assembly_revisions_in_products": nested} if nested else used
    if name == "dependents":
        return trace.run(name, Q.DEPENDENTS, {"item_id": args["item_id"]})
    if name == "exposure":
        iid = args["item_id"]
        own = trace.run("own_revisions", """MATCH (r:Revision) WHERE r.id = $id RETURN r.id AS id, r.status AS status
                                            UNION MATCH (:Item {id:$id})-[:HAS_REV]->(r:Revision)
                                            RETURN r.id AS id, r.status AS status""", {"id": iid})
        if own:  # a product or a revision: its own builds and shipments
            revs = [r["id"] for r in own]
            applicable, excluded = {r["id"]: 1 for r in own if r["status"] == "released"}, \
                {r["id"]: r["status"] for r in own if r["status"] != "released"}
        else:
            used = trace.run("where_used", Q.WHERE_USED, {"item_id": iid})
            revs = [u["revision"] for u in used if u["applicable"]]
            applicable = {u["revision"]: u["qty_per_unit"] for u in used if u["applicable"]}
            excluded = {u["revision"]: u["status"] for u in used if not u["applicable"]}
            revs_all = [u["revision"] for u in used]
        field = trace.run("field_units", """MATCH (s:Shipment)-[:OF_REV]->(r:Revision) WHERE r.id IN $revs
                                            OPTIONAL MATCH (s)-[:SHIPPED_TO]->(c:Customer)
                                            RETURN s.id AS shipment, r.id AS revision, r.status AS status, s.qty AS qty,
                                                   s.shipped_on AS shipped_on, c.name AS customer""",
                          {"revs": revs if own else revs_all})
        return {"applicable_revisions": applicable, "excluded_revisions": excluded,
                "builds": trace.run(name, Q.EXPOSURE, {"revisions": revs}), "field_units": field}
    if name == "alternates":
        alts = trace.run(name, Q.ALTERNATES, {"item_id": args["item_id"]})
        decisions = trace.run("decisions", Q.DECISIONS, {"item_id": args["item_id"]})
        from neura1.impact import alternate_status
        for a in alts:
            a["decisions"] = [d for d in decisions if d["subject"] == a["id"]]
            a["status"] = alternate_status(a["decisions"])
            a["approval"] = APPROVAL_TEXT[a["status"]]
            a["quotes"] = trace.run("quotes", Q.QUOTES, {"item_id": a["id"]})
        return alts
    if name == "decisions":
        return trace.run(name, Q.DECISIONS, {"item_id": args["item_id"]})
    if name == "quotes":
        if args.get("item_id"):
            return trace.run(name, Q.QUOTES, {"item_id": args["item_id"]})
        return trace.run("all_quotes", """MATCH (s:Supplier)-[:QUOTED]->(q:Quote)-[:FOR]->(i:Item)
                                           RETURN q.id AS id, i.id AS item, s.name AS supplier, q.unit_price AS unit_price,
                                                  q.currency AS currency, q.lead_weeks AS lead_weeks,
                                                  q.valid_from AS valid_from, q.valid_until AS valid_until
                                           ORDER BY valid_until""", {})
    if name == "organisation":
        leaders = trace.run("leadership", """MATCH (p:Person)-[:MEMBER_OF]->(:Team {id:'T-LEAD'})
                                              OPTIONAL MATCH (p)-[r:HOLDS_ROLE]->(o:Organization)
                                              RETURN p.name AS name, coalesce(r.role, p.role) AS title, o.name AS organisation
                                              ORDER BY name""", {})
        out = {"leadership": leaders}
        if args.get("name"):
            out["person"] = trace.run("reporting_line", """
                MATCH (p:Person) WHERE toLower(p.name) CONTAINS toLower($t)
                OPTIONAL MATCH (p)-[:REPORTS_TO]->(m:Person) OPTIONAL MATCH (r:Person)-[:REPORTS_TO]->(p)
                OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p) OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
                RETURN p.name AS name, p.role AS role, t.name AS team, m.name AS manager,
                       collect(DISTINCT r.name) AS direct_reports, collect(DISTINCT b.name) AS backed_up_by""",
                {"t": args["name"]})
        return out
    if name == "notices":
        return trace.run(name, """MATCH (s:Source {kind:'notice'})<-[:PART_OF]-(c:Chunk)
                                  WITH s, c ORDER BY c.ordinal
                                  RETURN s.id AS id, s.title AS title, collect(c.text) AS text""", {})
    if name == "search_documents":
        from neura1.search import hybrid
        r = hybrid(graph, args["query"], 6)
        return {"modes": r["modes"], "hits": [{k: h[k] for k in ("chunk", "title", "author", "ts", "text", "mentions")}
                                              for h in r["hits"]], "related": r["related"]}
    if name == "who_knows":
        r = brain.who_knows(graph, args["text"])
        trace.steps.extend(r.pop("trace"))
        return r
    if name == "person":
        found = trace.run("find_person", """MATCH (p:Person) WHERE toLower(p.name) CONTAINS toLower($t)
                                             OR p.id = $t RETURN p.id AS id""", {"t": args["name"]})
        if len(found) != 1:
            return {"error": f"{len(found)} people match {args['name']!r}"}
        r = brain.person(graph, found[0]["id"])
        trace.steps.extend(r.pop("trace"))
        r["finished_recently"] = trace.run("finished_work", """
            MATCH (a:Action)-[:ASSIGNED_TO]->(:Person {id:$id}) WHERE a.status = 'done'
            RETURN a.id AS id, a.title AS title, a.completed_at AS completed_at ORDER BY completed_at DESC LIMIT 8""",
            {"id": found[0]["id"]})
        r["reporting"] = trace.run("reporting", """
            MATCH (p:Person {id:$id}) OPTIONAL MATCH (p)-[:REPORTS_TO]->(m:Person)
            OPTIONAL MATCH (b:Person)-[:BACKS_UP]->(p) OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
            RETURN m.name AS manager, collect(b.name) AS backed_up_by, t.name AS team""", {"id": found[0]["id"]})
        return r
    if name == "project":
        found = trace.run("find_project", """MATCH (p:Project) WHERE toLower(p.name) CONTAINS toLower($t)
                                              OR toUpper(p.id) = toUpper($t) RETURN p.id AS id""", {"t": args["text"]})
        if len(found) != 1:
            return {"error": f"{len(found)} projects match {args['text']!r}", "hint": "use list_projects"}
        r = brain.project(graph, found[0]["id"])
        trace.steps.extend(r.pop("trace"))
        return r
    if name == "list_projects":
        return trace.run(name, brain.PROJECTS, {})
    if name == "recent_changes":
        r = brain.changes(graph, limit=15)
        trace.steps.extend(r.pop("trace"))
        return r
    if name == "absence_impact":
        found = trace.run("find_person", """MATCH (p:Person) WHERE toLower(p.name) CONTAINS toLower($t)
                                             OR p.id = $t RETURN p.id AS id""", {"t": args["name"]})
        if len(found) != 1:
            return {"error": f"{len(found)} people match {args['name']!r}"}
        r = scenarios.absence_impact(graph, found[0]["id"])
        trace.steps.extend(r.pop("trace"))
        return r
    if name == "customer":
        found = trace.run("find_customer", """MATCH (c:Customer) WHERE toLower(c.name) CONTAINS toLower($t)
                                               OR toUpper(c.id) = toUpper($t) RETURN c.id AS id""", {"t": args["text"]})
        if len(found) != 1:
            return {"error": f"{len(found)} customers match {args['text']!r}"}
        r = scenarios.customer_360(graph, found[0]["id"])
        trace.steps.extend(r.pop("trace"))
        return r
    if name == "risk_radar":
        r = scenarios.risk_radar(graph)
        trace.steps.extend(r.pop("trace"))
        return r
    if name == "recall":
        from neura1 import memory
        return memory.recall(graph, args["text"])
    if name == "propose_task":
        return {"draft": {k: args.get(k) for k in ("owner", "title", "target", "why")},
                "note": "Draft only. A person must confirm it in Neura1 before it exists."}
    if name == "read_only_cypher":
        q = guard_cypher(args["query"])
        return trace.run(name, q, {})
    if name == "change_impact":
        price = args.get("new_unit_price")
        r = analyse(graph, ChangeEvent(args["item_id"], Decimal(str(price)) if price is not None else None, "INR",
                                       None, args.get("lead_weeks"), date.today()))
        trace.steps.extend(s | {"name": f"change_impact.{s['name']}"} for s in r.pop("trace", []))
        # The full report is large; give the model the facts it needs to answer, not the drawing data.
        if r.get("status") != "ok":
            return r
        cost = r.get("cost") or {}
        return {
            "part": r["part"], "change": r["change"],
            "applicable_revisions": [w["revision"] for w in r["where_used"] if w["applicable"]],
            "excluded_revisions": {w["revision"]: w["status"] for w in r["where_used"] if not w["applicable"]},
            "builds": [{k: b[k] for k in ("build", "revision", "planned_date", "parts_needed", "from_stock", "shortfall",
                                          "supply_eta_if_ordered_today", "at_risk", "planner")}
                       | {"orders": [o["order"] for o in b["orders"]]} for b in r["builds"]],
            "field_units": r["field_units"],
            "cost": {k: cost.get(k) for k in ("baseline_quote", "baseline_unit_price", "new_unit_price", "net_need",
                                              "material_delta", "one_time_total", "total_delta", "formula", "assumptions")},
            "alternates": [{"id": a["id"], "status": a.get("status"), "decisions": [d["id"] for d in a.get("decisions", [])]}
                           for a in r.get("alternates", [])],
            "tasks": [{"owner": a["owner"], "title": a["title"]} for a in r.get("actions", [])],
        }
    raise ValueError(f"Unknown tool {name}")


def _catalogue() -> str:
    lines = []
    for name, desc, params in TOOLS:
        args = ", ".join(f"{k}: {v['type'] if isinstance(v['type'], str) else '/'.join(v['type'])}"
                         for k, v in params.items())
        lines.append(f"- {name}({args}): {desc}")
    return "\n".join(lines)


STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "enum": [t[0] for t in TOOLS] + ["answer"]},
        "args": {"type": "object"},
        "answer": {"type": "string"},
    },
    "required": ["tool"],
}

PLANNER = SYSTEM + """

You work in steps. At each step reply with ONE JSON object:
  {"tool": "<tool name>", "args": {...}}       to look something up, or
  {"tool": "answer", "answer": "<final answer>"} when the tool results are enough.
Tools:
""" + "{catalogue}"


CHUNK_ID = re.compile(r"^[\w./-]+\.(?:json|md|txt|pdf)#[\w-]+$")


def _collect(value, out: list):
    """Every passage id that appears anywhere in tool results: these are the answer's sources."""
    if isinstance(value, dict):
        for v in value.values():
            _collect(v, out)
    elif isinstance(value, list):
        for v in value:
            _collect(v, out)
    elif isinstance(value, str) and CHUNK_ID.match(value) and value not in out:
        out.append(value)


def _finish(graph: Graph, answer: str, calls: list, trace: Trace, results: list) -> dict:
    sources: list[str] = []
    _collect(results, sources)
    drafts = [r["draft"] for r in results if isinstance(r, dict) and "draft" in r]
    return {"answer": answer, "warnings": check_approval_claims(graph, answer), "tool_calls": calls,
            "sources": sources[:12], "drafts": drafts, "trace": trace.steps}


def _restrict(name: str, result, restrict: dict | None):
    """Remove what the reader may not see before the model ever reads it."""
    if not restrict:
        return result
    from neura1.access import redact_money, redact_money_text
    if not restrict.get("money"):
        result = redact_money_text(redact_money(result))
    if name == "absence_impact" and isinstance(result, dict) and result.get("person"):
        pid = result["person"].get("id")
        if not restrict.get("leave_of", lambda _p: True)(pid):
            return {"person": result["person"].get("name"), "restricted": "leave dates and handover details are not "
                    "visible to everyone reading this; point them to the person's page"}
    if name == "person" and isinstance(result, dict):
        result = {k: v for k, v in result.items() if k not in ("absences",)}
    return result


def ask(graph: Graph, question: str, max_steps: int = 10, history: list[dict] | None = None,
        on_step=None, restrict: dict | None = None) -> dict:
    """Plan-act loop using JSON output only, so it works on any OpenAI-compatible server,
    including local models whose native tool-call parsing is unreliable."""
    from neura1.llm import _parse_json

    c = client()
    trace = Trace(graph)
    calls, results = [], []
    messages = [{"role": "system", "content": PLANNER.replace("{catalogue}", _catalogue())}]
    for turn in history or []:  # earlier turns of this conversation, so follow-up questions make sense
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": json.dumps({"tool": "answer", "answer": turn["answer"]})})
    messages.append({"role": "user", "content": question})
    for _ in range(max_steps):
        try:
            resp = c.chat.completions.create(
                model=settings.llm_model, messages=messages, temperature=0,
                response_format={"type": "json_schema", "json_schema": {"name": "step", "schema": STEP_SCHEMA}})
            step = _parse_json(resp.choices[0].message.content or "")
        except Exception as exc:
            return _finish(graph, f"The model could not complete this question ({exc}).", calls, trace, results)
        if step.get("tool") == "answer" or step.get("tool") not in {t[0] for t in TOOLS}:
            return _finish(graph, (step.get("answer") or "").strip() or "No answer.", calls, trace, results)
        args = step.get("args") or {}
        if on_step:
            on_step({"type": "tool", "tool": step["tool"], "args": args})
        try:
            result = _restrict(step["tool"], run_tool(graph, trace, step["tool"], args), restrict)
        except Exception as exc:  # report tool errors back to the model instead of failing the request
            result = {"error": str(exc)}
        calls.append({"tool": step["tool"], "args": args})
        results.append(result)
        messages.append({"role": "assistant", "content": json.dumps(step)})
        messages.append({"role": "user", "content": f"Result of {step['tool']}:\n"
                         + json.dumps(result, default=str)[:6000]
                         + "\n\nNext step (another tool, or the answer)?"})
    messages.append({"role": "user", "content": "Give your final answer now from the results so far."})
    try:
        resp = c.chat.completions.create(
            model=settings.llm_model, messages=messages, temperature=0,
            response_format={"type": "json_schema", "json_schema": {"name": "step", "schema": STEP_SCHEMA}})
        answer = _parse_json(resp.choices[0].message.content or "").get("answer", "")
    except Exception:
        answer = ""
    return _finish(graph, answer or "I could not finish within the step limit.", calls, trace, results)
