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

SYSTEM = """You are Neura1, the company brain of Voltline Controls, an industrial electronics company.
Answer questions using ONLY the results of your tools. Rules:
- Call tools to look things up; never answer from memory or assumptions.
- Cite the ids you relied on (part numbers, revisions, orders, decisions like DEC-117, documents like TR-112).
- If the tools return nothing relevant, say plainly that it is not recorded. Do not guess.
- A part listed as an alternate is NOT approved unless its "approval" field says APPROVED. A passed bench test
  or a chat message is not an approval. Use the alternates tool and repeat its approval wording.
- Use ids exactly as the tools return them (e.g. NB54360, VC-200-C).
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
    for r in rows(graph, "MATCH (a:Item)-[:ALTERNATE_OF]-(:Item) RETURN DISTINCT a.id AS id"):
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
    ("resolve_item", "Find an item (product, assembly, part, firmware, test) by id or manufacturer part number.",
     {"text": {"type": "string"}}),
    ("where_used", "Which product revisions use an item, quantity per unit, and whether each revision is released.",
     {"item_id": {"type": "string"}}),
    ("change_impact", "Full impact of a price and/or lead-time change on a part: builds, orders, customers, "
                      "dependencies, alternates with decisions, cost scenario and required tasks.",
     {"item_id": {"type": "string"}, "new_unit_price": {"type": ["number", "null"]},
      "lead_weeks": {"type": ["integer", "null"]}}),
    ("dependents", "Firmware modules, test procedures and other items that depend on a part, with their owners.",
     {"item_id": {"type": "string"}}),
    ("exposure", "Planned builds, customer orders (with due dates and penalty notes), customers and account "
                 "managers that use a part on released revisions.",
     {"item_id": {"type": "string"}}),
    ("decisions", "Recorded decisions about an item or its alternates, with who decided and verbatim evidence.",
     {"item_id": {"type": "string"}}),
    ("alternates", "Alternate parts listed for a part, with their quotes and approval status.",
     {"item_id": {"type": "string"}}),
    ("quotes", "Supplier quotes for an item, with validity dates.", {"item_id": {"type": "string"}}),
    ("who_knows", "Who knows about something: a part, project, customer, order or alias like 'pmic_seq.c'. "
                  "Returns people ranked with the reasons (owns it, decided, discussed, works on it).",
     {"text": {"type": "string"}}),
    ("person", "A person's profile: role, team, backup, what they own, projects, decisions, open tasks, topics.",
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
    ("propose_task", "Draft a task for a person. It is NOT created until a human confirms it. Use when the user "
                     "asks to assign, follow up, or get something done.",
     {"owner": {"type": "string"}, "title": {"type": "string"}, "target": {"type": ["string", "null"]},
      "why": {"type": "string"}}),
    ("search_documents", "Full-text search over chats, tickets, reports and notices.", {"query": {"type": "string"}}),
    ("read_only_cypher", "Run a read-only Cypher query on the company graph when no other tool fits. Labels: Item, "
                         "Revision, Supplier, Quote, Build, Order, Customer, Shipment, Person, Team, Source, Chunk, "
                         "Decision, Investigation, Action. See docs/data-model.md.",
     {"query": {"type": "string"}}),
]


def run_tool(graph: Graph, trace: Trace, name: str, args: dict):
    if name == "resolve_item":
        return trace.run(name, Q.RESOLVE_ITEM, {"text": args["text"]})
    if name == "where_used":
        return trace.run(name, Q.WHERE_USED, {"item_id": args["item_id"]})
    if name == "dependents":
        return trace.run(name, Q.DEPENDENTS, {"item_id": args["item_id"]})
    if name == "exposure":
        used = trace.run("where_used", Q.WHERE_USED, {"item_id": args["item_id"]})
        revs = [u["revision"] for u in used if u["applicable"]]
        return {"applicable_revisions": {u["revision"]: u["qty_per_unit"] for u in used if u["applicable"]},
                "excluded_revisions": {u["revision"]: u["status"] for u in used if not u["applicable"]},
                "builds": trace.run(name, Q.EXPOSURE, {"revisions": revs})}
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
        return trace.run(name, Q.QUOTES, {"item_id": args["item_id"]})
    if name == "search_documents":
        return trace.run(name, Q.SEARCH_PASSAGES, {"q": args["query"], "limit": 6})
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
        for k in ("where_used",):
            r.pop(k, None)
        return r
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


def ask(graph: Graph, question: str, max_steps: int = 6) -> dict:
    """Plan-act loop using JSON output only, so it works on any OpenAI-compatible server,
    including local models whose native tool-call parsing is unreliable."""
    from neura1.llm import _parse_json

    c = client()
    trace = Trace(graph)
    calls, results = [], []
    messages = [{"role": "system", "content": PLANNER.replace("{catalogue}", _catalogue())},
                {"role": "user", "content": question}]
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
        try:
            result = run_tool(graph, trace, step["tool"], args)
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
