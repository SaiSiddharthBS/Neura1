"""Neura1 HTTP API. Run: uv run uvicorn neura1.main:app --reload --port 8000"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeout

from neura1 import access, actions, agent, brain, people as people_mod, queries as Q, scenarios
from neura1.config import settings
from neura1.graph import GraphUnavailable, get_graph, rows
from neura1.impact import ChangeEvent, analyse
from neura1.ingest import extract
from neura1.ingest.structured import LOADERS, ensure_indexes, existing_ids, load_rows, read_csv
from neura1.ingest.unstructured import SUPPORTED, load_sources
from neura1.ingest.validate import ORDER, SPECS, template_csv, validate
from neura1.llm import LLMUnavailable
from neura1.viz import impact_subgraph

app = FastAPI(title="Neura1", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RedisConnectionError)
@app.exception_handler(RedisTimeout)
@app.exception_handler(GraphUnavailable)
async def graph_down(_: Request, exc: GraphUnavailable):
    return JSONResponse(status_code=503, content={
        "error": "graph_unavailable",
        "detail": "FalkorDB is unreachable, so graph-based analysis is unavailable. No fallback answer is given.",
    })


@app.exception_handler(LLMUnavailable)
async def llm_down(_: Request, exc: LLMUnavailable):
    return JSONResponse(status_code=503, content={"error": "model_unavailable", "detail": str(exc)})


def require_passcode(x_demo_passcode: str | None = Header(default=None)):
    if x_demo_passcode != settings.demo_passcode:
        raise HTTPException(status_code=403, detail="Writes need the demo passcode")


def graph():
    return get_graph()


def current_viewer(x_neura1_as: str | None = Header(default=None), g=Depends(graph)) -> access.Viewer:
    """The person the web app is acting for. Drives what money and leave details are visible."""
    return access.viewer(g, x_neura1_as)


def guard_money(payload, v: access.Viewer):
    if v.sees_money:
        return payload
    out = access.redact_money(payload)
    if isinstance(out, dict):
        out["restricted"] = sorted(set(out.get("restricted", [])) | {"money"}) if isinstance(out.get("restricted"), list) else ["money"]
    return out


@app.get("/api/health")
def health():
    try:
        n = rows(get_graph(), "MATCH (n) RETURN count(n) AS n")[0]["n"]
        return {"graph": "ok", "nodes": n, "model": settings.llm_model or None}
    except Exception as exc:
        raise GraphUnavailable(str(exc))


@app.get("/api/overview")
def overview(g=Depends(graph)):
    labels = rows(g, "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY n DESC")
    rels = rows(g, "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS n ORDER BY n DESC")
    teams = rows(g, """MATCH (t:Team)<-[:MEMBER_OF]-(p:Person)
                       OPTIONAL MATCH (p)-[:OWNS]->(x)
                       RETURN t.name AS team, collect(DISTINCT {name: p.name, role: p.role}) AS people,
                              collect(DISTINCT x.id) AS owns ORDER BY team""")
    sources = rows(g, """MATCH (s:Source) WHERE s.kind <> 'export'
                         OPTIONAL MATCH (s)<-[:PART_OF]-(c:Chunk)
                         RETURN s.id AS id, s.kind AS kind, s.title AS title, count(c) AS passages ORDER BY id""")
    return {"labels": labels, "relationships": rels, "teams": teams, "sources": sources}


# ---------- notices ----------

def _notice_snapshot(source_id: str) -> dict | None:
    path = extract.snapshot_path(source_id, "notice")
    if not path.exists():
        return None
    snap = json.loads(path.read_text())
    text = "\n".join(p["text"] for p in extract.source_passages(get_graph(), source_id))
    snap["problems"] = extract.verify_notice(snap["output"], text)
    return snap


@app.get("/api/notices")
def notices(g=Depends(graph)):
    found = rows(g, "MATCH (s:Source {kind:'notice'}) RETURN s.id AS id, s.title AS title, s.version AS version")
    return [n | {"extraction": _notice_snapshot(n["id"])} for n in found]


@app.post("/api/notices/extract", dependencies=[Depends(require_passcode)])
def extract_notice(source_id: str, g=Depends(graph)):
    snap = extract.run_model(g, source_id, "notice")
    return _notice_snapshot(snap["source_id"])


@app.post("/api/notices", dependencies=[Depends(require_passcode)])
async def add_notice(text: str | None = Form(None), file: UploadFile | None = File(None), g=Depends(graph)):
    """Paste a supplier email or upload a PDF/text notice. The model reads it if one is connected."""
    from datetime import datetime

    inbox = settings.data_dir / "uploads" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if file is not None and file.filename:
        blob = await file.read(MAX_UPLOAD + 1)
        if len(blob) > MAX_UPLOAD:
            raise HTTPException(413, "Notice larger than 5 MB")
        suffix = Path(file.filename).suffix.lower()
        if suffix not in (".pdf", ".md", ".txt"):
            raise HTTPException(415, "Upload a .pdf, .txt or .md notice, or paste the text")
        path = inbox / f"notice-{stamp}{suffix}"
        path.write_bytes(blob)
    elif text and text.strip():
        first = text.strip().splitlines()[0][:120]
        path = inbox / f"notice-{stamp}.md"
        path.write_text(text if first.startswith("#") else f"# {first}\n\n{text}")
    else:
        raise HTTPException(400, "Paste the notice text or upload a file")
    load_sources(g, root=settings.data_dir, files=[path])
    source_id = str(path.relative_to(settings.data_dir))
    model_error = None
    try:
        extract.run_model(g, source_id, "notice")
    except LLMUnavailable as exc:
        model_error = str(exc)
    except Exception as exc:  # a model failure must not lose the notice; the user can enter the facts
        model_error = f"Model could not read the notice: {exc}"
    return {"source_id": source_id, "extraction": _notice_snapshot(source_id), "model_error": model_error}


class NoticeFields(BaseModel):
    source_id: str
    part: str
    new_unit_price: float | None = None
    currency: str = "INR"
    effective_date: str | None = None
    lead_weeks: int | None = None
    last_time_buy: str | None = None
    entered_by: str


@app.post("/api/notices/manual", dependencies=[Depends(require_passcode)])
def notice_manual(body: NoticeFields):
    change_types = [t for t, v in (("price", body.new_unit_price), ("lead_time", body.lead_weeks),
                                   ("lifecycle", body.last_time_buy)) if v is not None]
    fields = body.model_dump(exclude={"source_id", "entered_by"}) | {"change_types": change_types}
    extract.save_manual_notice(body.source_id, fields, body.entered_by)
    return _notice_snapshot(body.source_id)


# ---------- impact ----------

class ChangeIn(BaseModel):
    item: str
    new_unit_price: Decimal | None = None
    currency: str = "INR"
    effective_date: date | None = None
    lead_weeks: int | None = None
    as_of: date | None = None
    source_id: str | None = None


@app.post("/api/impact")
def impact(change: ChangeIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    return guard_money(_impact(change, g), v)


def _impact(change: ChangeIn, g):
    event = ChangeEvent(**change.model_dump(exclude={"as_of"}), as_of=change.as_of or date.today())
    report = analyse(g, event)
    if report["status"] != "ok":
        return report
    report["graph"] = impact_subgraph(report)
    inv = actions.find_investigation(g, report["part"]["id"], change.source_id)
    report["investigation"] = inv
    report["changes_since_approval"] = diff_snapshots(inv["snapshot"], actions.snapshot_of(report)) \
        if inv and inv.get("snapshot") else []
    return report


def diff_snapshots(old: dict, new: dict) -> list[str]:
    """Human-readable changes between the facts at approval time and now. Tolerates older, partial snapshots."""
    out = []
    for key, label in (("cost_total", "Cost increase"), ("baseline_quote", "Baseline quote")):
        if key in old and old[key] != new[key]:
            out.append(f"{label} changed from {old[key]} to {new[key]}")
    old_alts, old_quotes = old.get("alternates", {}), old.get("alternate_quotes", {})
    for alt, status in new["alternates"].items():
        if "alternates" in old and old_alts.get(alt) != status:
            out.append(f"{alt}: {old_alts.get(alt, 'not listed').replace('_', ' ')} → {status.replace('_', ' ')}")
        added = set(new["alternate_quotes"].get(alt, [])) - set(old_quotes.get(alt, []))
        if "alternate_quotes" in old and added:
            out.append(f"New quote for {alt}: {', '.join(sorted(added))}")
    for key, label in (("builds_at_risk", "Builds at risk"), ("revisions", "Affected revisions"),
                       ("decisions", "Recorded decisions")):
        if key in old and old[key] != new[key]:
            out.append(f"{label}: {', '.join(old[key]) or 'none'} → {', '.join(new[key]) or 'none'}")
    return out


@app.post("/api/impact/notice")
def impact_from_notice(source_id: str, as_of: date | None = None, g=Depends(graph),
                       v: access.Viewer = Depends(current_viewer)):
    return guard_money(_impact_from_notice(source_id, as_of, g), v)


def _impact_from_notice(source_id: str, as_of: date | None, g):
    snap = _notice_snapshot(source_id)
    if snap is None:
        raise HTTPException(404, "This notice has not been extracted yet")
    if snap["problems"]:
        raise HTTPException(422, {"detail": "Extraction failed verification", "problems": snap["problems"]})
    n = snap["output"]
    return _impact(ChangeIn(item=n["part"], new_unit_price=n["new_unit_price"],
                           currency=extract.normalise_currency(n.get("currency")) or "INR",
                           effective_date=n["effective_date"], lead_weeks=n["lead_weeks"], as_of=as_of,
                           source_id=source_id), g)


# ---------- evidence ----------

@app.get("/api/evidence")
def evidence(chunk_id: str, g=Depends(graph)):
    found = rows(g, """
        MATCH (c:Chunk {id:$id})-[:PART_OF]->(s:Source)
        OPTIONAL MATCH (c)-[:MENTIONS]->(m)
        OPTIONAL MATCH (s)<-[:PART_OF]-(sib:Chunk)
        WITH c, s, collect(DISTINCT m.id) AS mentions, sib ORDER BY sib.ordinal
        RETURN c.id AS id, c.text AS text, c.author AS author, c.ts AS ts, c.page AS page,
               c.source_version AS source_version, s.id AS source, s.title AS title, s.kind AS kind,
               s.version AS current_version, mentions,
               collect({id: sib.id, text: sib.text, author: sib.author, ts: sib.ts, page: sib.page}) AS context
    """, {"id": chunk_id})
    if not found:
        raise HTTPException(404, "Unknown passage")
    return found[0] | {"stale": found[0]["source_version"] != found[0]["current_version"]}


@app.get("/api/search")
def search(q: str, limit: int = 8, g=Depends(graph)):
    """Hybrid semantic + keyword search, expanded to the records each passage mentions."""
    from neura1 import search as hybrid_search
    return hybrid_search.hybrid(g, q, min(limit, 25))


# ---------- actions ----------

class ApproveIn(BaseModel):
    item_id: str
    source_id: str | None = None
    approved_by: str
    new_unit_price: str | None = None
    lead_weeks: int | None = None
    currency: str | None = "INR"


@app.post("/api/actions/approve", dependencies=[Depends(require_passcode)])
def approve(body: ApproveIn, as_of: date | None = None, g=Depends(graph)):
    """Re-runs the analysis server-side so the stored snapshot reflects the graph, not what a client sent."""
    report = analyse(g, ChangeEvent(body.item_id, Decimal(body.new_unit_price) if body.new_unit_price else None,
                                    body.currency or "INR", None, body.lead_weeks, as_of or date.today(),
                                    body.source_id))
    if report["status"] != "ok":
        raise HTTPException(404, "Unknown item")
    cost = report["cost"]
    return actions.approve(g, report["part"]["id"], body.source_id, report["actions"], body.approved_by,
                           str(cost["total_delta"]) if cost else None, cost["currency"] if cost else None,
                           actions.snapshot_of(report))


@app.get("/api/investigations")
def investigations(g=Depends(graph)):
    return rows(g, """
        MATCH (inv:Investigation)-[:CONCERNS]->(i)
        OPTIONAL MATCH (inv)-[:TRIGGERED_BY]->(s:Source)
        OPTIONAL MATCH (inv)-[:PRODUCED]->(a:Action)
        RETURN inv.id AS id, i.id AS item, coalesce(inv.kind, 'supplier_change') AS kind, labels(i)[0] AS label, s.id AS source, s.title AS source_title, inv.created_at AS created_at,
               inv.approved_by AS approved_by, inv.cost_total AS cost_total, inv.currency AS currency,
               count(a) AS actions ORDER BY created_at DESC""")


# ---------- live updates (demo) ----------

UPDATES = settings.fixture_dir / "updates"


@app.post("/api/updates/apply", dependencies=[Depends(require_passcode)])
def apply_updates(g=Depends(graph)):
    """Bring in the facts that arrive mid-demo: a new quote, a chat message, and a bench note."""
    quote_cypher = dict(LOADERS)["quotes.csv"]
    loaded = {}
    for path in sorted(UPDATES.glob("*.csv")):
        src = f"updates/{path.name}"
        for r in read_csv(path):
            g.query(quote_cypher, {"r": r, "src": src, "auth": "system_of_record"})
        loaded[src] = "quotes"
    docs = sorted(p for p in UPDATES.glob("*") if p.suffix in (".json", ".md"))
    loaded |= load_sources(g, files=docs)
    decisions = {}
    for path in docs:
        sid = str(path.relative_to(settings.fixture_dir))
        snap_path = extract.snapshot_path(sid, "decisions")
        if snap_path.exists():
            decisions[sid] = extract.load_decisions(g, json.loads(snap_path.read_text()))
    return {"loaded": loaded, "decisions": decisions}


# ---------- onboarding: a company's own exports and documents ----------

@app.get("/api/import/templates")
def templates():
    return [{"name": s.name, "title": s.title, "columns": s.columns, "required": s.required, "help": s.help}
            for s in (SPECS[n] for n in ORDER)]


@app.get("/api/import/templates/{name}.csv", response_class=PlainTextResponse)
def template(name: str):
    if name not in SPECS:
        raise HTTPException(404, "No such template")
    return PlainTextResponse(template_csv(name), headers={"Content-Disposition": f"attachment; filename={name}.csv"})


MAX_UPLOAD = 5 * 1024 * 1024


async def _read_uploads(files: list[UploadFile]) -> tuple[dict[str, str], dict[str, bytes], list[str]]:
    csvs, docs, skipped = {}, {}, []
    for f in files:
        blob = await f.read(MAX_UPLOAD + 1)
        name = Path(f.filename or "upload").name
        if len(blob) > MAX_UPLOAD:
            skipped.append(f"{name}: larger than 5 MB")
        elif name.endswith(".csv"):
            csvs[name] = blob.decode("utf-8-sig", errors="replace")
        elif Path(name).suffix in SUPPORTED:
            docs[name] = blob
        else:
            skipped.append(f"{name}: unsupported type (use .csv, .md, .txt, .pdf, or Slack/ticket .json)")
    return csvs, docs, skipped


@app.post("/api/import/validate")
async def import_validate(files: list[UploadFile] = File(...), eda_parent_rev: str | None = Form(None),
                          g=Depends(graph)):
    csvs, docs, skipped = await _read_uploads(files)
    report = validate(csvs, existing_ids(g), eda_parent_rev or None) if csvs else {"ok": True, "files": [], "issues": [], "errors": 0,
                                                            "warnings": 0}
    report.pop("_parsed", None)
    return report | {"documents": sorted(docs), "skipped": skipped}


@app.post("/api/import/commit", dependencies=[Depends(require_passcode)])
async def import_commit(files: list[UploadFile] = File(...), eda_parent_rev: str | None = Form(None),
                        g=Depends(graph)):
    csvs, docs, skipped = await _read_uploads(files)
    report = validate(csvs, existing_ids(g), eda_parent_rev or None) if csvs else {"ok": True, "_parsed": {}}
    if not report["ok"]:
        raise HTTPException(422, "Validation failed; nothing was imported")
    ensure_indexes(g)
    loaded = {kind: load_rows(g, kind, report["_parsed"][kind], f"import/{kind}.csv")
              for kind in ORDER if kind in report["_parsed"]}
    saved = []
    upload_dir = settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    for name, blob in docs.items():
        path = upload_dir / name
        path.write_bytes(blob)
        saved.append(path)
    passages = load_sources(g, root=settings.data_dir, files=saved) if saved else {}
    return {"records": loaded, "documents": passages, "skipped": skipped}


# ---------- ask ----------

class AskIn(BaseModel):
    question: str
    conversation_id: str | None = None


def _ask(g, body: AskIn, v: access.Viewer, on_step=None) -> dict:
    from neura1 import memory
    if len(body.question) > 500:
        raise HTTPException(400, "Question too long")
    cid = body.conversation_id or memory.start(g, v.id, body.question)
    result = agent.ask(g, body.question, history=memory.history(g, cid), on_step=on_step)
    result |= memory.record(g, cid, body.question, result)
    return guard_money(result, v)


@app.post("/api/ask")
def ask(body: AskIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    return _ask(g, body, v)


@app.post("/api/ask/stream")
def ask_stream(body: AskIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    """Server-sent events: each tool call as it happens, then the full answer."""
    import queue
    import threading
    from fastapi.responses import StreamingResponse

    q: queue.Queue = queue.Queue()

    def work():
        try:
            q.put({"type": "answer", **_ask(g, body, v, on_step=q.put)})
        except Exception as exc:  # surface model or graph errors to the client
            q.put({"type": "error", "detail": getattr(exc, "detail", None) or str(exc)})
        q.put(None)

    threading.Thread(target=work, daemon=True).start()

    def events():
        yield "event: start\ndata: {}\n\n"
        while (item := q.get()) is not None:
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/conversations")
def conversations(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import memory
    return memory.conversations(g, v.id)


@app.get("/api/conversations/{conversation_id}")
def conversation(conversation_id: str, g=Depends(graph)):
    from neura1 import memory
    return memory.transcript(g, conversation_id)


# ---------- the wider company brain ----------

@app.get("/api/lookup")
def lookup(q: str, g=Depends(graph)):
    return rows(g, brain.LOOKUP, {"q": q[:80]}) if len(q.strip()) >= 2 else []


@app.get("/api/brain/who-knows")
def who_knows(q: str, g=Depends(graph)):
    return brain.who_knows(g, q)


@app.get("/api/people")
def people(g=Depends(graph)):
    return rows(g, brain.PEOPLE)


@app.get("/api/people/{person_id}")
def person(person_id: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    found = people_mod.person_360(g, person_id, v)
    if not found:
        raise HTTPException(404, "Unknown person")
    return found


@app.get("/api/projects")
def projects(g=Depends(graph)):
    return rows(g, brain.PROJECTS)


@app.get("/api/projects/{project_id}")
def project(project_id: str, g=Depends(graph)):
    found = brain.project(g, project_id)
    if not found:
        raise HTTPException(404, "Unknown project")
    return found


@app.get("/api/changes")
def changes(today: date | None = None, g=Depends(graph)):
    return brain.changes(g, today)


class TaskIn(BaseModel):
    title: str
    owner: str | None = None
    target: str | None = None
    why: str = ""
    created_by: str
    cites: list[str] = []


@app.post("/api/tasks", dependencies=[Depends(require_passcode)])
def create_task(body: TaskIn, g=Depends(graph)):
    return actions.create_task(g, body.title, body.owner, body.target, body.why, body.created_by, body.cites)


# ---------- workboard ----------

@app.get("/api/board")
def board(g=Depends(graph)):
    return actions.board(g)


class StatusIn(BaseModel):
    status: str
    by: str
    note: str | None = None


@app.post("/api/actions/{action_id}/status", dependencies=[Depends(require_passcode)])
def move_task(action_id: str, body: StatusIn, g=Depends(graph)):
    try:
        return actions.set_status(g, action_id, body.status, body.by, body.note)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except KeyError:
        raise HTTPException(404, "Unknown task")


# ---------- company events beyond supplier changes ----------

@app.get("/api/signals")
def signals(g=Depends(graph)):
    return scenarios.signals(g)


@app.get("/api/scenarios/absence/{person_id}")
def absence(person_id: str, start: str | None = None, end: str | None = None, g=Depends(graph),
            v: access.Viewer = Depends(current_viewer)):
    r = scenarios.absence_impact(g, person_id, start, end)
    if r["status"] != "ok":
        raise HTTPException(404, "Unknown person")
    if not v.sees_leave_of(person_id):
        return {"status": "restricted", "person": {"name": r["person"]["name"]},
                "detail": "Leave plans are visible to the person, their management chain, their backup, HR and leadership."}
    r["investigation"] = actions.find_investigation(g, person_id, _signal_for(g, "leave", person_id))
    return r


@app.get("/api/customers")
def customers(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    return guard_money(rows(g, scenarios.CUSTOMERS), v)


@app.get("/api/customers/{customer_id}")
def customer(customer_id: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    return guard_money(_customer(customer_id, g), v)


def _customer(customer_id: str, g):
    r = scenarios.customer_360(g, customer_id)
    if r["status"] != "ok":
        raise HTTPException(404, "Unknown customer")
    r["investigation"] = actions.find_investigation(g, customer_id, r["escalation"])
    return r


@app.get("/api/risk")
def risk(today: date | None = None, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    return guard_money(scenarios.risk_radar(g, today), v)


def _signal_for(g, kind: str, subject: str) -> str | None:
    return next((s["id"] for s in scenarios.signals(g) if s["kind"] == kind and s["subject"] == subject), None)


class PlanIn(BaseModel):
    kind: str
    subject_id: str
    approved_by: str


@app.post("/api/plans/approve", dependencies=[Depends(require_passcode)])
def approve_plan(body: PlanIn, g=Depends(graph)):
    """Approve the plan for a person's absence or a customer escalation; recomputed on the server."""
    if body.kind == "absence":
        r = scenarios.absence_impact(g, body.subject_id)
        source = _signal_for(g, "leave", body.subject_id)
        snapshot = {"tasks": [a["title"] for a in r.get("actions", [])]}
    elif body.kind == "escalation":
        r = scenarios.customer_360(g, body.subject_id)
        source = r.get("escalation")
        snapshot = {"tasks": [a["title"] for a in r.get("actions", [])]}
    else:
        raise HTTPException(422, "kind must be absence or escalation")
    if r["status"] != "ok":
        raise HTTPException(404, "Unknown subject")
    return actions.approve(g, body.subject_id, source, r["actions"], body.approved_by, None, None, snapshot,
                           kind=body.kind)


# ---------- people, organisation, my day ----------

@app.get("/api/viewer")
def who_am_i(v: access.Viewer = Depends(current_viewer)):
    return v.describe()


@app.get("/api/org")
def org(g=Depends(graph)):
    return people_mod.org_chart(g)


@app.get("/api/me")
def me(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    return guard_money(people_mod.my_day(g, v), v)


class PersonPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    team_id: str | None = None
    manager_id: str | None = None
    backup_id: str | None = None
    add_skills: list[str] = []
    remove_skills: list[str] = []
    absence: dict | None = None
    by: str


@app.patch("/api/people/{person_id}", dependencies=[Depends(require_passcode)])
def edit_person(person_id: str, body: PersonPatch, g=Depends(graph)):
    try:
        return people_mod.update_person(g, person_id, body.model_dump(exclude={"by"}, exclude_none=True), body.by)
    except KeyError:
        raise HTTPException(404, "Unknown person")


class PersonNew(BaseModel):
    id: str
    name: str
    role: str
    team_id: str | None = None
    by: str


@app.post("/api/people", dependencies=[Depends(require_passcode)])
def new_person(body: PersonNew, g=Depends(graph)):
    try:
        return people_mod.add_person(g, body.id.strip().upper(), body.name, body.role, body.team_id, body.by)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/teams")
def teams(g=Depends(graph)):
    return rows(g, "MATCH (t:Team) RETURN t.id AS id, t.name AS name ORDER BY name")


# ---------- live ingestion ----------

@app.post("/api/webhooks/slack")
async def slack_webhook(request: Request, g=Depends(graph)):
    from neura1 import webhooks
    body = await request.body()
    if settings.slack_signing_secret:
        if not webhooks.verify_slack(settings.slack_signing_secret, request.headers.get("x-slack-request-timestamp", ""),
                                     body, request.headers.get("x-slack-signature", "")):
            raise HTTPException(401, "Bad Slack signature")
    elif request.headers.get("x-neura1-webhook-secret") != settings.webhook_secret:
        raise HTTPException(401, "Webhook secret required")
    return webhooks.slack_event(g, json.loads(body or b"{}"))


@app.post("/api/webhooks/jira")
async def jira_webhook(request: Request, g=Depends(graph)):
    from neura1 import webhooks
    if request.headers.get("x-neura1-webhook-secret") != settings.webhook_secret:
        raise HTTPException(401, "Webhook secret required")
    return webhooks.jira_event(g, await request.json())


@app.get("/api/action-items")
def action_items(g=Depends(graph)):
    return rows(g, brain.ACTION_ITEMS)
