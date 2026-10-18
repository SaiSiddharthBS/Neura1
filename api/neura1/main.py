"""Neura1 HTTP API. Run: uv run uvicorn neura1.main:app --reload --port 8000"""

import json
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeout

from neura1 import access, actions, agent, brain, chat, people as people_mod, scenarios
from neura1.config import settings
from neura1.graph import GraphUnavailable, get_graph, rows
from neura1.impact import ChangeEvent, analyse
from neura1.ingest import extract
from neura1.ingest.structured import LOADERS, ensure_indexes, existing_ids, load_rows, read_csv
from neura1.ingest.unstructured import SUPPORTED, load_sources
from neura1.ingest.validate import ORDER, SPECS, template_csv, validate
from neura1.llm import LLMUnavailable
from neura1.viz import impact_subgraph

@asynccontextmanager
async def lifespan(_app):
    """Background jobs: the mail-drop inbox, the 09:00 IST morning brief and the DGX worker that reads new
    information (off when NEURA1_BACKGROUND=0)."""
    if settings.background:
        from neura1 import auto, brief, inbox
        inbox.start_watcher(get_graph)
        brief.start_scheduler(get_graph)
        if settings.auto_extract:
            auto.start(get_graph)
        if settings.erp_sync_minutes > 0:
            from neura1.connect import scheduler
            scheduler.start(get_graph)
    from neura1 import agent_mcp
    async with agent_mcp.mcp.session_manager.run():  # the remote MCP endpoint for cloud agents (off without a token)
        yield


app = FastAPI(title="Neura1", version="0.1.0", lifespan=lifespan)


def _mount_agent_mcp():
    from neura1 import agent_mcp
    app.mount("/api/agent", agent_mcp.gated_app)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def hide_amounts_in_text(request: Request, call_next):
    """Safety net under the per-endpoint rules, whichever page or query produced the response:
    - for anyone who may not see money, no rupee amount written in a message, answer or note leaves the API;
    - for anyone who may not see a person's leave, no passage of that person's leave notice leaves the API."""
    response = await call_next(request)
    who = request.headers.get("x-neura1-as")
    if not who or not request.url.path.startswith("/api/") or response.headers.get("content-type") != "application/json":
        return response
    try:
        g = get_graph()
        v = access.viewer(g, who)
        hidden = access.hidden_sources(g, v.sees_leave_of)
    except Exception:
        return response
    if v.sees_money and not hidden:
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    data = json.loads(body)
    headers = {k: val for k, val in response.headers.items() if k.lower() != "content-length"}
    if hidden:
        if access.points_at_hidden(data, hidden):
            return JSONResponse({"detail": "This leave notice is visible to the person, their backup, "
                                           "and the directors and leadership team"}, status_code=403)
        data = access.drop_hidden(data, hidden)
    if not v.sees_money:
        data = access.redact_money_text(data)
    return JSONResponse(data, status_code=response.status_code, headers=headers)


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


_ai_calls: dict[str, list[float]] = {}


def ai_rate_limit(request: Request):
    """A public demo shares one model: at most 8 AI requests a minute from one visitor."""
    import time
    who = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0].strip() \
        or (request.client.host if request.client else "local")
    now = time.monotonic()
    recent = [t for t in _ai_calls.get(who, []) if now - t < 60]
    if len(recent) >= settings.ai_per_minute:
        raise HTTPException(429, "Neura1 is answering a lot of questions right now. Please try again in a minute.")
    _ai_calls[who] = recent + [now]


def require_passcode(x_demo_passcode: str | None = Header(default=None)):
    """Changes are open unless NEURA1_DEMO_PASSCODE is set; then they need it."""
    if settings.demo_passcode and x_demo_passcode != settings.demo_passcode:
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
        from neura1 import llm as _llm
        from neura1 import auto
        return {"graph": "ok", "nodes": n, **(_llm.status() if settings.llm_model else {"model": None}),
                "worker": auto.last_run or None, "passcode_required": bool(settings.demo_passcode)}
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
    sources = rows(g, """MATCH (s:Source) WHERE NOT s.kind IN ['export', 'dm']
                         OPTIONAL MATCH (s)<-[:PART_OF]-(c:Chunk)
                         RETURN s.id AS id, s.kind AS kind, s.title AS title, count(c) AS passages ORDER BY id""")
    return {"labels": labels, "relationships": rels, "teams": teams, "sources": sources}


# ---------- notices ----------

def _notice_snapshot(source_id: str) -> dict | None:
    path = extract.snapshot_path(source_id, "notice")
    if not path.exists():
        return None
    g = get_graph()
    snap = extract.with_resolved_part(g, json.loads(path.read_text()))
    text = "\n".join(p["text"] for p in extract.source_passages(g, source_id))
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
    from neura1 import inbox
    r = inbox.ingest(g, path, "notice")
    return {"source_id": r["source_id"], "extraction": _notice_snapshot(r["source_id"]), "model_error": r["model_error"]}


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
    result = actions.approve(g, report["part"]["id"], body.source_id, report["actions"], body.approved_by,
                             str(cost["total_delta"]) if cost else None, cost["currency"] if cost else None,
                             actions.snapshot_of(report))
    if result["created"]:
        owners = sorted({a["owner"] for a in report["actions"] if a["owner"]})
        chat.notify(g, "plan", f"{body.approved_by} approved the {report['part']['id']} change plan: "
                    f"{len(result['created'])} tasks for {', '.join(owners)}.",
                    [{"label": "Open impact", "href": f"/impact?item={report['part']['id']}"}, {"label": "Workboard", "href": "/board"}])
    return result


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
    found = [d for r in decisions.values() for d in r["written"]]
    chat.notify(g, "evidence", f"New information arrived: {len(loaded)} sources"
                + (f", including recorded evidence {', '.join(found)}" if found else "")
                + ". Open plans that depend on it show what changed.", [{"label": "What's new", "href": "/changes"}])
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
    restrict = None if v.unrestricted else {"money": v.sees_money, "leave_of": v.sees_leave_of,
                                            "hidden": access.hidden_sources(g, v.sees_leave_of)}
    result = agent.ask(g, body.question, history=memory.history(g, cid), on_step=on_step, restrict=restrict)
    result |= memory.record(g, cid, body.question, result)
    return guard_money(result, v)


@app.post("/api/ask", dependencies=[Depends(ai_rate_limit)])
def ask(body: AskIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    return _ask(g, body, v)


@app.post("/api/ask/stream", dependencies=[Depends(ai_rate_limit)])
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
def conversation(conversation_id: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import memory
    owner = rows(g, "MATCH (c:Conversation {id:$id}) OPTIONAL MATCH (p:Person)-[:STARTED]->(c) "
                    "RETURN coalesce(c.private, false) AS private, p.id AS by", {"id": conversation_id})
    if owner and owner[0]["private"] and not v.unrestricted and owner[0]["by"] != v.id:
        raise HTTPException(403, "This conversation happened in a direct message")
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


# ---------- Connect: the ERP and project planner, over MCP ----------

def require_leader(v: access.Viewer = Depends(current_viewer)) -> access.Viewer:
    if not (v.unrestricted or v.leader):
        raise HTTPException(403, "Only the directors and leadership can change what Neura1 syncs")
    return v


@app.get("/api/connect")
def connect_status(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1.connect import sync
    return {"source": sync.describe(), "runs": sync.history(g), "can_sync": v.unrestricted or v.leader}


@app.post("/api/connect/zoho/test")
def connect_test(v: access.Viewer = Depends(require_leader)):
    from neura1.connect import sync
    return sync.probe()


class SyncIn(BaseModel):
    dry_run: bool = False


@app.post("/api/connect/zoho/sync")
def connect_sync(body: SyncIn, g=Depends(graph), v: access.Viewer = Depends(require_leader)):
    from neura1 import alerts
    from neura1.connect import sync
    from neura1 import agent_mcp
    report = sync.run(g, dry_run=body.dry_run, by=v.name)
    if report.get("run") and settings.agent_alert_webhook and agent_mcp.sharing_on():
        alerts.post(f"Neura1 synced {len(report['changes'])} change(s) from Zoho:\n"
                    + "\n".join(f"• {c['summary']}" for c in report["changes"][:8]))
    return report


# ---------- agents in the cloud (OpenAI Dots and other MCP clients) ----------

@app.get("/api/agents")
def agents_status(g=Depends(graph)):
    from neura1 import agent_mcp
    v = agent_mcp.agent_viewer(g)
    tools = [{"name": t.name, "description": (t.description or "").split("\n")[0]}
             for t in agent_mcp.mcp._tool_manager.list_tools()]
    share = agent_mcp.sharing(g)
    return {"sharing": share | {"configured": bool(settings.agent_mcp_token)},
            "mcp": {"enabled": bool(settings.agent_mcp_token) and share["enabled"], "path": "/api/agent/mcp",
                    "transport": "Streamable HTTP",
                    "read_as": v.name, "sees_money": v.sees_money, "sees_leave": v.unrestricted or v.leader,
                    "tools": tools},
            "alerts": {"enabled": bool(settings.agent_alert_webhook) and share["enabled"],
                       "configured": bool(settings.agent_alert_webhook)}}


class SharingIn(BaseModel):
    enabled: bool


@app.post("/api/agents/sharing")
def agents_sharing(body: SharingIn, g=Depends(graph), v: access.Viewer = Depends(require_leader)):
    """The one switch for anything leaving Neura1: the remote MCP endpoint for agents and alerts to Slack or Teams."""
    from neura1 import agent_mcp
    return agent_mcp.set_sharing(g, body.enabled, v.name)


@app.post("/api/agents/test")
def agents_test(request: Request, v: access.Viewer = Depends(require_leader)):
    """Connect to Neura1's own remote MCP endpoint as an agent would, list its tools and call one."""
    import anyio
    from mcp import Client
    from neura1 import agent_mcp
    if not settings.agent_mcp_token:
        return {"ok": False, "error": "Agent access is not set up. Set NEURA1_AGENT_MCP_TOKEN."}
    if not agent_mcp.sharing_on():
        return {"ok": False, "error": "External AI access is switched off. Switch it on above to let agents connect."}
    host, port = request.scope.get("server") or ("127.0.0.1", 8000)
    url = f"http://{host}:{port}/api/agent/{settings.agent_mcp_token}/mcp"

    async def go():
        async with Client(url, read_timeout_seconds=60) as c:
            tools = [t.name for t in (await c.list_tools()).tools]
            r = await c.call_tool("timeline_deviations", {})
            data = json.loads("".join(getattr(x, "text", "") for x in r.content))
            return {"ok": True, "tools": tools, "sample": {"tool": "timeline_deviations", "summary": data["summary"],
                                                           "read_as": data["read_as"]}}
    try:
        return anyio.run(go)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/api/agents/alert")
def agents_alert(g=Depends(graph), v: access.Viewer = Depends(require_leader)):
    from neura1 import agent_mcp, alerts
    text = alerts.digest(g)
    if not agent_mcp.sharing_on():
        return {"text": text, "sent": False, "reason": "external sharing is off, so it stays in Neura1"}
    return {"text": text} | alerts.post(text)


# ---------- department agents ----------

@app.get("/api/departments")
def departments_status(g=Depends(graph)):
    from neura1 import departments
    return departments.status(g)


@app.post("/api/departments/{agent_id}/run")
def departments_run(agent_id: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import departments
    if agent_id != "all" and agent_id not in departments.BY_ID:
        raise HTTPException(404, "No such agent")
    ids = [a["id"] for a in departments.AGENTS] if agent_id == "all" else [agent_id]
    return [departments.run(g, i) for i in ids]


@app.get("/api/gantt")
def get_gantt(today: date | None = None, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    """Every project, task, build and customer order with baseline, plan and forecast dates, and the deviation."""
    from neura1 import timeline
    return timeline.timeline(g, v, today)


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
        moved = actions.set_status(g, action_id, body.status, body.by, body.note)
        if body.status == "done":
            title = rows(g, "MATCH (a:Action {id:$id}) RETURN a.title AS t", {"id": action_id})[0]["t"]
            chat.notify(g, "task_done", f"Done: {title} ({body.by}).", [{"label": "Workboard", "href": "/board"}])
        return moved
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
                "detail": "Leave plans are visible to the person, their backup, and the directors and leadership team."}
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
    result = actions.approve(g, body.subject_id, source, r["actions"], body.approved_by, None, None, snapshot,
                             kind=body.kind)
    if result["created"]:
        name = r["person"]["name"] if body.kind == "absence" else r["customer"]["name"]
        what = "handover plan" if body.kind == "absence" else "escalation plan"
        owners = sorted({a["owner"] for a in r["actions"] if a["owner"]})
        chat.notify(g, "escalation" if body.kind == "escalation" else "absence",
                    f"{body.approved_by} approved the {what} for {name}: {len(result['created'])} tasks for {', '.join(owners)}.",
                    [{"label": "Workboard", "href": "/board"}])
    return result


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


# ---------- Neura1 Chat ----------

def _chat(fn, *args, **kwargs):
    """Run a chat operation, turning its refusals into HTTP errors."""
    try:
        return fn(*args, **kwargs)
    except chat.ChatError as exc:
        raise HTTPException(exc.status, str(exc))


def _chat_member(g, channel_id: str, v: access.Viewer) -> dict:
    ch = chat.channel(g, channel_id)
    if not ch:
        raise HTTPException(404, "Unknown conversation")
    _chat(chat.may_read, ch, v)
    return ch


def _me(v: access.Viewer) -> str:
    if not v.id:
        raise HTTPException(400, "Choose who you are first")
    return v.id


@app.get("/api/chat/channels")
def chat_channels(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    return [c for c in chat.channels(g, v.id, v.name) if v.sees_money or c["id"] not in chat.MONEY_CHANNELS]


@app.get("/api/chat/unread")
def chat_unread(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    if not v.id:
        return {"total": 0, "mentions": 0, "conversations": 0}
    cs = [c for c in chat.channels(g, v.id, v.name) if v.sees_money or c["id"] not in chat.MONEY_CHANNELS]
    return {"total": sum(c["unread"] for c in cs), "mentions": sum(c["mentions"] for c in cs),
            "conversations": sum(1 for c in cs if c["unread"])}


class DmIn(BaseModel):
    person_id: str


@app.post("/api/chat/bot")
def chat_bot(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    """The viewer's own conversation with Neura1 (created on first use)."""
    return {"id": _chat(chat.bot_channel, g, _me(v))}


@app.post("/api/chat/dm")
def chat_dm(body: DmIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    return {"id": _chat(chat.dm_channel, g, _me(v), body.person_id)}


class GroupIn(BaseModel):
    name: str
    members: list[str]


@app.post("/api/chat/groups", dependencies=[Depends(require_passcode)])
def chat_group(body: GroupIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    return {"id": _chat(chat.create_group, g, _me(v), body.name, body.members)}


class ChannelIn(BaseModel):
    name: str
    purpose: str | None = None


@app.post("/api/chat/channels", dependencies=[Depends(require_passcode)])
def chat_new_channel(body: ChannelIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    return {"id": _chat(chat.create_channel, g, _me(v), body.name, body.purpose)}


class ConversationEdit(BaseModel):
    channel: str
    name: str | None = None
    purpose: str | None = None


@app.patch("/api/chat/channels", dependencies=[Depends(require_passcode)])
def chat_edit_channel(body: ConversationEdit, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    _chat_member(g, body.channel, v)
    _chat(chat.update_conversation, g, body.channel, _me(v), body.name, body.purpose)
    return chat.channel(g, body.channel)


class MembersIn(BaseModel):
    channel: str
    add: list[str] = []
    remove: str | None = None


@app.post("/api/chat/members", dependencies=[Depends(require_passcode)])
def chat_members(body: MembersIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    _chat_member(g, body.channel, v)
    members = None
    if body.add:
        members = _chat(chat.add_members, g, body.channel, _me(v), body.add)
    if body.remove:
        members = _chat(chat.remove_member, g, body.channel, _me(v), body.remove)
    return {"members": members}


@app.get("/api/chat/messages")
def chat_messages(channel: str, after: str | None = None, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    ch = _chat_member(g, channel, v)
    chat.seen(v.id)
    cursor = chat.recent_cursor()
    return {"messages": chat.messages(g, channel, after), "cursor": cursor,
            "typing": chat.who_is_typing(channel, v.id),
            "read": chat.read_state(g, channel) if ch["kind"] in chat.PRIVATE else {}}


class ChatIn(BaseModel):
    channel: str
    text: str
    reply_to: str | None = None


@app.post("/api/chat/messages", dependencies=[Depends(require_passcode)])
def chat_post(body: ChatIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    me = _me(v)
    if not body.text.strip() or len(body.text) > chat.MAX_TEXT:
        raise HTTPException(400, "Message is empty or too long")
    chat.ensure_channels(g)
    _chat_member(g, body.channel, v)
    if body.reply_to and not body.reply_to.startswith(body.channel + "#"):
        raise HTTPException(400, "You can only reply to a message in the same conversation")
    return chat.handle(g, body.channel, body.text.strip(), v.name, me, body.reply_to)


class EditIn(BaseModel):
    id: str
    text: str


@app.patch("/api/chat/messages", dependencies=[Depends(require_passcode)])
def chat_edit(body: EditIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    _chat_member(g, body.id.split("#", 1)[0], v)
    return _chat(chat.edit_message, g, body.id, _me(v), body.text)


class MessageRef(BaseModel):
    id: str


@app.post("/api/chat/messages/delete", dependencies=[Depends(require_passcode)])
def chat_delete(body: MessageRef, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    _chat_member(g, body.id.split("#", 1)[0], v)
    return _chat(chat.delete_message, g, body.id, _me(v))


class ReactIn(BaseModel):
    id: str
    emoji: str


@app.post("/api/chat/react", dependencies=[Depends(require_passcode)])
def chat_react(body: ReactIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    _chat_member(g, body.id.split("#", 1)[0], v)
    return _chat(chat.react, g, body.id, _me(v), body.emoji)


class ChannelRef(BaseModel):
    channel: str


@app.post("/api/chat/read")
def chat_read(body: ChannelRef, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    """Read markers and typing are conversation metadata, so they need no passcode."""
    _chat_member(g, body.channel, v)
    chat.mark_read(g, body.channel, _me(v))
    return {"ok": True}


@app.post("/api/chat/typing")
def chat_typing(body: ChannelRef, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    _chat_member(g, body.channel, v)
    chat.typing(body.channel, _me(v), v.name)
    return {"ok": True}


@app.get("/api/chat/search")
def chat_search(q: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    _me(v)
    return chat.search(g, v, q)


# ---------- never the same mistake twice ----------

class GuardIn(BaseModel):
    text: str


@app.post("/api/guard")
def guard_check(body: GuardIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    """Check a message or draft against recorded decisions, quotes, revisions and leave while it is written."""
    from neura1 import guard
    if len(body.text) > 8000:
        raise HTTPException(400, "Text is too long to check")
    return {"flags": guard.check(g, body.text, v)}


# ---------- inventory ----------

@app.get("/api/inventory")
def inventory_list(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import inventory
    out = inventory.items(g)
    return out if v.sees_money else access.redact_money(out)


@app.get("/api/inventory/{item_id}")
def inventory_item(item_id: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import inventory
    out = inventory.item(g, item_id)
    if out.get("status") != "ok":
        raise HTTPException(404, f"No part called {item_id}")
    out["money_visible"] = v.sees_money
    return out if v.sees_money else access.redact_money(out)


# ---------- purchasing: Neura1 drafts, a person approves ----------

def _buyer(v: access.Viewer) -> str:
    if not v.id or not (v.leader or v.unrestricted):
        raise HTTPException(403, "Purchase orders carry prices, so they are raised and received by the directors and "
                                 "the leadership team")
    return v.name


@app.get("/api/purchasing/draft")
def purchasing_draft(item: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import purchasing
    _buyer(v)
    try:
        return purchasing.suggest(g, item, by=v.name)
    except purchasing.PurchasingError as exc:
        raise HTTPException(400, str(exc))


class RaiseIn(BaseModel):
    item: str
    qty: int | None = None


@app.post("/api/purchasing/orders", dependencies=[Depends(require_passcode)])
def purchasing_raise(body: RaiseIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import purchasing
    by = _buyer(v)
    try:
        return purchasing.create(g, body.item, body.qty, by)
    except purchasing.PurchasingError as exc:
        raise HTTPException(400, str(exc))


class ReceiveIn(BaseModel):
    po: str
    qty: int
    rejected: int = 0
    lot: str | None = None


@app.post("/api/purchasing/receive", dependencies=[Depends(require_passcode)])
def purchasing_receive(body: ReceiveIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import purchasing
    by = _buyer(v)
    try:
        return purchasing.receive(g, body.po, body.qty, body.rejected, (body.lot or "").strip()[:40] or None, by)
    except purchasing.PurchasingError as exc:
        raise HTTPException(400, str(exc))


# ---------- meetings ----------

@app.get("/api/meetings")
def meetings_list(g=Depends(graph)):
    from neura1 import meetings
    return meetings.list_meetings(g)


@app.post("/api/meetings", dependencies=[Depends(require_passcode)])
async def meetings_upload(file: UploadFile = File(...), title: str | None = Form(None), g=Depends(graph),
                          v: access.Viewer = Depends(current_viewer)):
    from neura1 import meetings
    if not v.id:
        raise HTTPException(400, "Choose who you are first")
    data = await file.read()
    try:
        return {"id": meetings.start(g, file.filename or "recording", data, title, v.name)}
    except meetings.MeetingError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/meetings/sample", dependencies=[Depends(require_passcode)])
def meetings_sample(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    """The synthetic BO-0415 build sync recording from the fixture."""
    from neura1 import meetings
    path = settings.fixture_dir / "samples" / "meeting_BO-0415_build_sync.m4a"
    if not path.exists():
        raise HTTPException(404, "The sample recording is missing")
    return {"id": meetings.start(g, path.name, path.read_bytes(), "BO-0415 build sync", v.name or "Demo")}


@app.get("/api/meetings/{meeting_id}")
def meetings_get(meeting_id: str, g=Depends(graph)):
    from neura1 import meetings
    out = meetings.get(g, meeting_id)
    if not out:
        raise HTTPException(404, "Unknown meeting")
    return out


@app.get("/api/meetings/{meeting_id}/audio")
def meetings_audio(meeting_id: str):
    from fastapi.responses import FileResponse
    from neura1 import meetings
    path = meetings.audio_path(meeting_id)
    if not path:
        raise HTTPException(404, "No recording")
    kinds = {".m4a": "audio/mp4", ".mp4": "audio/mp4", ".mp3": "audio/mpeg", ".mpeg": "audio/mpeg", ".wav": "audio/wav",
             ".aiff": "audio/aiff", ".aif": "audio/aiff", ".ogg": "audio/ogg", ".webm": "audio/webm", ".flac": "audio/flac"}
    return FileResponse(path, media_type=kinds.get(path.suffix.lower(), "application/octet-stream"))


# ---------- knowledge health ----------

@app.get("/api/knowledge-health")
def knowledge_health_sweep(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import knowledge_health
    return knowledge_health.sweep(g, v)


class ReviewRequest(BaseModel):
    source: str


@app.post("/api/knowledge-health/review", dependencies=[Depends(require_passcode)])
def knowledge_health_review(body: ReviewRequest, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import knowledge_health
    if not v.id:
        raise HTTPException(400, "Choose who you are first")
    try:
        return knowledge_health.request_review(g, body.source, v)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ---------- can we promise this? ----------

class PromiseIn(BaseModel):
    product: str
    qty: int
    due: date


@app.post("/api/promise")
def promise_check(body: PromiseIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import promise
    if not 0 < body.qty <= 100000:
        raise HTTPException(400, "Quantity must be between 1 and 100,000")
    return promise.check(g, body.product, body.qty, body.due, v)


@app.get("/api/promise/products")
def promise_products(g=Depends(graph)):
    return rows(g, """MATCH (i:Item {kind:'product'})-[:HAS_REV]->(r:Revision)
                      RETURN i.id AS product, i.name AS name, r.id AS revision, r.status AS status ORDER BY revision""")


# ---------- company sandbox ----------

def _leadership(v: access.Viewer) -> None:
    if not (v.unrestricted or v.leader):
        raise HTTPException(403, "The sandbox weighs amounts and leave plans together, so it is open to the directors "
                                 "and the leadership team")


@app.get("/api/sandbox/presets")
def sandbox_presets(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import sandbox
    _leadership(v)
    return [p | {"labels": [s["label"] for s in sandbox.validate(g, p["shocks"])]} for p in sandbox.PRESETS]


@app.get("/api/sandbox/options")
def sandbox_options(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    _leadership(v)
    return {
        "parts": rows(g, "MATCH (i:Item {kind:'part'}) RETURN i.id AS id, i.name AS name ORDER BY id"),
        "people": rows(g, "MATCH (p:Person) RETURN p.id AS id, p.name AS name ORDER BY name"),
        "orders": rows(g, "MATCH (c:Customer)-[:PLACED]->(o:Order) RETURN o.id AS id, c.name AS customer, "
                          "o.qty AS qty, o.due_date AS due ORDER BY id"),
        "suppliers": rows(g, "MATCH (s:Supplier) RETURN s.id AS id, s.name AS name ORDER BY name"),
    }


class SandboxIn(BaseModel):
    shocks: list[dict]


@app.post("/api/sandbox")
def sandbox_run(body: SandboxIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import sandbox
    _leadership(v)
    try:
        return sandbox.run(g, body.shocks)
    except (sandbox.SandboxError, ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc))


# ---------- knowledge rescue ----------

@app.get("/api/rescue")
def rescue_plan(person: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import rescue
    if not v.sees_profile_of(person):
        raise HTTPException(403, "Knowledge rescue is open to the person themself, and to the directors and "
                                 "leadership team")
    out = rescue.plan(g, person)
    if out.get("status") != "ok":
        raise HTTPException(404, "Unknown person")
    if not v.sees_leave_of(person):
        out["absence"] = None
    return out


@app.get("/api/rescue/candidates")
def rescue_candidates(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    """People whose knowledge is most at risk: away soon, or owning things. Others see only themselves."""
    if not (v.unrestricted or v.leader):
        return [{"id": v.id, "name": v.name, "reason": "you"}] if v.id else []
    away = {r["id"]: r for r in rows(g, """MATCH (p:Person)-[:HAS_ABSENCE]->(a:Absence) WHERE a.end_date >= $t
                                          RETURN p.id AS id, a.start_date AS start, a.end_date AS end""",
                                     {"t": date.today().isoformat()})}
    owners = rows(g, "MATCH (p:Person)-[:OWNS]->(i:Item) RETURN p.id AS id, p.name AS name, collect(i.id) AS owns")
    out = []
    for o in owners:
        a = away.get(o["id"])
        out.append({"id": o["id"], "name": o["name"], "owns": o["owns"],
                    "reason": f"away {a['start']} to {a['end']}" if a else f"owns {', '.join(o['owns'][:3])}"})
    return sorted(out, key=lambda x: (not x["reason"].startswith("away"), x["name"]))


class RescueAnswer(BaseModel):
    person: str
    question_id: str
    question: str
    about: list[str] = []
    answer: str


@app.post("/api/rescue/answer", dependencies=[Depends(require_passcode)])
def rescue_answer(body: RescueAnswer, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import rescue
    if not v.id or not (v.id == body.person or v.leader):
        raise HTTPException(403, "Only the person, or the leadership team recording for them, can add answers")
    if not body.answer.strip() or len(body.answer) > 6000:
        raise HTTPException(400, "The answer is empty or too long")
    try:
        return rescue.save(g, body.person, body.question_id, body.question, body.about, body.answer,
                           None if v.id == body.person else v.name)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


class ReviewIn(BaseModel):
    question: str
    answer: str


@app.post("/api/rescue/review", dependencies=[Depends(ai_rate_limit)])
def rescue_review(body: ReviewIn, v: access.Viewer = Depends(current_viewer)):
    from neura1 import rescue
    if len(body.answer) > 6000:
        raise HTTPException(400, "The answer is too long")
    return rescue.review(body.question, body.answer)


# ---------- graph explorer ----------

@app.get("/api/explore")
def explore(id: str, g=Depends(graph)):
    from neura1 import explore as ex
    return ex.neighborhood(g, id)


@app.get("/api/timeline")
def record_timeline(id: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import explore as ex
    events = ex.timeline(g, id)
    if not v.sees_leave_of(id):
        events = [e for e in events if e["kind"] != "leave"]
    if not v.sees_money:
        events = [e if e["kind"] != "quote" else e | {"detail": "price hidden for your role"} for e in events]
    return events


# ---------- Neura1 Docs ----------

def _doc_or_404(g, doc_id: str, v: access.Viewer) -> dict:
    from neura1 import documents
    d = documents.get(g, doc_id)
    if not d:
        raise HTTPException(404, "Unknown document")
    if not documents.may_open(d, v):
        raise HTTPException(403, "This document states amounts; it is open to the directors and the leadership team")
    return d


@app.get("/api/docs")
def docs_list(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import documents
    return documents.list_docs(g, v)


class DocCreateIn(BaseModel):
    template: str = "blank"          # blank | change_notice | customer_response | handover | import
    record: str | None = None
    title: str | None = None
    markdown: str | None = None      # for imports


@app.post("/api/docs", dependencies=[Depends(require_passcode)])
def docs_create(body: DocCreateIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import documents
    if not v.id:
        raise HTTPException(400, "Choose who you are first")
    try:
        if body.template == "change_notice":
            notice = next((s["id"] for s in scenarios.signals(g) if s["kind"] == "notice"
                           and s["subject"] == body.record), None)
            report = _impact_from_notice(notice, None, g) if notice else _impact(ChangeIn(item=body.record or ""), g)
            if report.get("status") != "ok":
                raise HTTPException(404, "Unknown part")
            title, md = documents.change_notice(g, report, v)
        elif body.template == "customer_response":
            title, md = documents.customer_response(g, body.record or "", v)
        elif body.template == "handover":
            title, md = documents.handover_note(g, body.record or "", v)
        elif body.template == "import":
            title, md = body.title or "Imported document", body.markdown or ""
        else:
            title, md = body.title or "Untitled document", f"# {body.title or 'Untitled document'}\n\n"
    except KeyError:
        raise HTTPException(404, "Unknown record")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    doc_id = documents.create(g, title, body.template, v, body.record)
    return {"id": doc_id, "title": title, "markdown": md}


@app.get("/api/docs/{doc_id}")
def docs_get(doc_id: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import documents
    d = _doc_or_404(g, doc_id, v)
    return d | {"has_file": documents.file_path(doc_id).exists()}


@app.get("/api/docs/{doc_id}/file")
def docs_file(doc_id: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from fastapi.responses import FileResponse
    from neura1 import documents
    d = _doc_or_404(g, doc_id, v)
    path = documents.file_path(doc_id)
    if not path.exists():
        raise HTTPException(404, "Not saved yet")
    return FileResponse(path, filename=f"{d['title']}.docx",
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.put("/api/docs/{doc_id}", dependencies=[Depends(require_passcode)])
async def docs_save(doc_id: str, file: UploadFile = File(...), title: str = Form(...), blocks: str = Form("[]"),
                    g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import documents
    _doc_or_404(g, doc_id, v)
    data = await file.read()
    if not data.startswith(b"PK") or len(data) > 25 * 1024 * 1024:
        raise HTTPException(400, "Expected a .docx file under 25 MB")
    texts = [b if isinstance(b, str) else b.get("text", "") for b in json.loads(blocks)]
    return documents.save(g, doc_id, data, title.strip() or "Untitled document", texts, v)


class BlocksIn(BaseModel):
    blocks: list[dict]
    instruction: str = ""
    title: str = ""


@app.post("/api/docs/check")
def docs_check(body: BlocksIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import documents
    return {"flags": documents.check(g, body.blocks, v)}


@app.post("/api/docs/ai", dependencies=[Depends(ai_rate_limit)])
def docs_ai(body: BlocksIn, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import documents
    if not body.instruction.strip():
        raise HTTPException(400, "Say what to change")
    try:
        return documents.ai_edit(g, body.instruction.strip(), body.blocks, v, body.title)
    except ValueError as exc:
        raise HTTPException(413, str(exc))
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc))


@app.get("/api/docs-insert")
def docs_insert(kind: str, record: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import documents
    try:
        return {"markdown": documents.insert_block(g, kind, record, v)}
    except (KeyError, ValueError) as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/docs-import")
async def docs_import(file: UploadFile = File(...)):
    from neura1 import documents
    name = file.filename or "document.txt"
    if not name.lower().endswith((".pdf", ".md", ".txt")):
        raise HTTPException(400, "Open .docx files directly; import .pdf, .md or .txt here")
    data = await file.read()
    try:
        title, md = documents.import_text(name, data)
    except Exception as exc:
        raise HTTPException(422, f"Could not read this file: {exc}")
    return {"title": title, "markdown": md}


# ---------- capability map ----------

@app.get("/api/capabilities")
def capability_map(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import capabilities
    return capabilities.company_map(g, v)


@app.get("/api/people/{person_id}/expertise")
def person_expertise(person_id: str, g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import capabilities
    return capabilities.person_expertise(g, person_id, v)


# ---------- demo reset ----------

_reset = {"running": False, "last": None, "error": None}


@app.post("/api/admin/reset", dependencies=[Depends(require_passcode)])
def reset_demo():
    """Rebuild the demo company from the fixture (records, documents, verified extractions, skill tags)."""
    import threading

    if _reset["running"]:
        return {"status": "running"}

    def work():
        from datetime import datetime, timezone
        from neura1.cli import load
        _reset.update(running=True, error=None)
        try:
            load()
            from neura1 import guard, meetings
            guard.forget()
            meetings.forget_jobs()
            for f in meetings.folder().glob("MTG-*"):
                f.unlink(missing_ok=True)
            for f in (settings.data_dir / "documents").glob("DOC-*"):
                f.unlink(missing_ok=True)
            _reset["last"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        except Exception as exc:  # reported to whoever asked for the reset
            _reset["error"] = str(exc)
        finally:
            _reset["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return {"status": "started"}


@app.get("/api/admin/reset")
def reset_status():
    return _reset


# ---------- proactive: morning brief and the mail-drop inbox ----------

@app.get("/api/brief")
def brief_today(g=Depends(graph)):
    from neura1 import brief
    return brief.compose(g)


@app.post("/api/brief", dependencies=[Depends(require_passcode)])
def brief_send(g=Depends(graph)):
    from neura1 import brief
    return brief.post(g, force=True)


@app.get("/api/brief/me")
def brief_mine(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import brief
    if not v.id:
        raise HTTPException(400, "Choose who you are first")
    return brief.personal(g, v.id)


@app.post("/api/brief/me", dependencies=[Depends(require_passcode)])
def brief_send_mine(g=Depends(graph), v: access.Viewer = Depends(current_viewer)):
    from neura1 import brief
    if not v.id:
        raise HTTPException(400, "Choose who you are first")
    return brief.post_personal(g, v.id, force=True)


@app.post("/api/inbox/check", dependencies=[Depends(require_passcode)])
def inbox_check(g=Depends(graph)):
    """Process the mail drop now (the background watcher also does this every few seconds)."""
    from neura1 import inbox
    return {"processed": inbox.process_drop(g), "folder": str(inbox.drop_dir())}


@app.post("/api/inbox", dependencies=[Depends(require_passcode)])
async def inbox_upload(file: UploadFile = File(...), g=Depends(graph)):
    """Forward an email (.eml) or drop a notice (.pdf, .md, .txt): it is classified and handled like the mail drop."""
    from neura1 import inbox
    name = Path(file.filename or "message.eml").name
    if Path(name).suffix.lower() not in (".eml", ".pdf", ".md", ".txt"):
        raise HTTPException(415, "Forward an email (.eml) or drop a .pdf, .md or .txt notice")
    blob = await file.read(MAX_UPLOAD + 1)
    if len(blob) > MAX_UPLOAD:
        raise HTTPException(413, "File larger than 5 MB")
    # Staged outside the watched folder, so the background watcher never picks the same file up twice.
    staged = inbox.drop_dir() / "incoming"
    staged.mkdir(exist_ok=True)
    path = staged / name
    path.write_bytes(blob)
    with inbox._lock:
        return {"processed": inbox.process_file(g, path)}


_mount_agent_mcp()  # after every /api route, so the mount never shadows one
