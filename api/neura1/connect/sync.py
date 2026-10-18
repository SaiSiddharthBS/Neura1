"""Neura1 Connect: keep the company graph in step with the ERP and the project planner, over MCP.

Neura1 is an add-on to the systems a company already plans in. Connect reads them through the Model Context Protocol,
the same open standard Zoho's MCP service (mcp.zoho.com) speaks, so no export or spreadsheet sits in between:

  1. fetch: call the source's MCP tools (items, purchase orders, goods received, projects, tasks);
  2. map: turn the source's records into Neura1's record types (Zoho's field names, date formats and statuses);
  3. diff: compare field by field with what the graph holds now; only new and changed records go further;
  4. validate: the same checks as a file import (types, enums, references); nothing is written if any fails;
  5. load: through the same loaders as every import, so baselines, inventory and the timeline update at once;
  6. record: a SyncRun with every change, shown in What's new and on the Connect page.

The demo source is a simulated Zoho (neura1.connect.zoho_sim) launched as a subprocess over stdio. Pointing Connect at
a real Zoho MCP server is configuration: NEURA1_ERP_MCP_URL (Streamable HTTP) and, if its tool names differ,
NEURA1_ERP_TOOLS, a JSON map from Neura1's names to the server's.
"""

import csv
import io
import json
import os
import sys
import uuid
from datetime import date, datetime, timezone

import anyio
from falkordb import Graph
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from neura1.config import REPO_ROOT, settings
from neura1.graph import rows
from neura1.ingest.structured import existing_ids, load_rows
from neura1.ingest.validate import ORDER, SPECS, validate

TOOLS = ("list_items", "list_purchase_orders", "list_purchase_receives", "list_projects", "list_tasks")
KINDS = ("stock", "purchase_orders", "receipts", "stock_moves", "projects", "tasks")


# ---------- the source ----------

def describe() -> dict:
    real = bool(settings.erp_mcp_url)
    return {"id": "zoho", "title": "Zoho Inventory + Zoho Projects", "transport": "Streamable HTTP" if real else "stdio",
            "simulated": not real, "endpoint": "configured (NEURA1_ERP_MCP_URL)" if real else "python -m neura1.connect.zoho_sim",
            "reads": ["Items and stock on hand", "Purchase orders", "Goods received", "Projects", "Tasks and their dates"],
            "schedule_minutes": settings.erp_sync_minutes}


def _server():
    if settings.erp_mcp_url:
        return settings.erp_mcp_url
    return StdioServerParameters(command=sys.executable, args=["-m", "neura1.connect.zoho_sim"],
                                 env=dict(os.environ), cwd=str(REPO_ROOT / "api"))


def _tool(name: str) -> str:
    names = json.loads(settings.erp_tools) if settings.erp_tools else {}
    return names.get(name, name)


def _payload(result) -> dict:
    text = "".join(getattr(c, "text", "") for c in result.content)
    data = json.loads(text) if text else {}
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"The source reported an error: {data['error']}")
    return data


async def _fetch(server) -> dict:
    async with Client(server, read_timeout_seconds=60) as client:
        tools = sorted(t.name for t in (await client.list_tools()).tools)
        out = {"tools": tools}
        for name in ("list_items", "list_purchase_orders", "list_purchase_receives", "list_projects"):
            out[name] = _payload(await client.call_tool(_tool(name), {}))
        out["list_tasks"] = {}
        for p in out["list_projects"].get("projects", []):
            out["list_tasks"][p["id"]] = _payload(await client.call_tool(_tool("list_tasks"), {"project_id": p["id"]}))
        return out


def fetch(server=None) -> dict:
    return anyio.run(_fetch, server or _server())


async def _probe(server) -> dict:
    async with Client(server, read_timeout_seconds=30) as client:
        tools = (await client.list_tools()).tools
        return {"ok": True, "tools": [{"name": t.name, "description": (t.description or "").split("\n")[0]} for t in tools]}


def probe(server=None) -> dict:
    try:
        return anyio.run(_probe, server or _server())
    except Exception as exc:  # report, never crash the page
        return {"ok": False, "error": str(exc)}


# ---------- map: Zoho's records to Neura1's ----------

PO_STATUS = {"draft": "open", "issued": "open", "open": "open", "partially_received": "partially_received",
             "received": "received", "billed": "received", "closed": "received", "cancelled": "cancelled"}
TASK_STATUS = {"open": "open", "in progress": "in_progress", "on hold": "blocked", "closed": "done",
               "completed": "done"}


def _iso_mdy(s: str | None) -> str:
    """Zoho Projects dates are MM-DD-YYYY."""
    if not s:
        return ""
    m, d, y = s.split(" ")[0].split("-")
    return date(int(y), int(m), int(d)).isoformat()


def to_records(raw: dict, graph: Graph) -> tuple[dict[str, list[dict]], list[str]]:
    """Zoho payloads → partial Neura1 rows (only the fields Zoho holds), and anything that could not be matched."""
    warnings: list[str] = []
    suppliers = {r["name"]: r["id"] for r in rows(graph, "MATCH (s:Supplier) RETURN s.id AS id, s.name AS name")}
    people = {r["name"].lower(): r["id"] for r in rows(graph, "MATCH (p:Person) RETURN p.id AS id, p.name AS name")}
    projects = {r["name"]: r for r in rows(graph, "MATCH (p:Project) RETURN p.id AS id, p.name AS name, p.status AS status")}
    out: dict[str, list[dict]] = {k: [] for k in KINDS}

    for i in raw["list_items"].get("items", []):
        if i.get("stock_on_hand") is not None:
            out["stock"].append({"item_id": i["sku"], "on_hand": str(int(i["stock_on_hand"]))})

    for po in raw["list_purchase_orders"].get("purchaseorders", []):
        supplier = suppliers.get(po["vendor_name"])
        if not supplier:
            warnings.append(f"{po['purchaseorder_number']}: vendor {po['vendor_name']!r} is not a supplier in Neura1")
            continue
        for li in po["line_items"]:
            out["purchase_orders"].append({
                "id": po["purchaseorder_number"], "supplier_id": supplier, "item_id": li["sku"], "qty": str(int(li["quantity"])),
                "unit_price": _num(li["purchase_rate"]), "currency": po.get("currency_code") or "INR",
                "ordered_on": po["date"], "expected_on": po.get("delivery_date") or "",
                "status": PO_STATUS.get(str(po["status"]).lower(), "open"), "quote_id": po.get("reference_number") or ""})

    for g in raw["list_purchase_receives"].get("purchasereceives", []):
        for li in g["line_items"]:
            out["receipts"].append({"id": g["receive_number"], "po_id": g["purchaseorder_number"], "item_id": li["sku"],
                                    "qty": str(int(li["quantity"])), "received_on": g["date"],
                                    "location": g.get("location_name") or "", "note": g.get("notes") or ""})

    by_zoho = {}
    for p in raw["list_projects"].get("projects", []):
        if p["name"] == "General":
            by_zoho[p["id"]] = ""
            continue
        mine = projects.get(p["name"])
        if not mine:
            warnings.append(f"Zoho project {p['name']!r} has no matching project in Neura1; its tasks were skipped")
            continue
        by_zoho[p["id"]] = mine["id"]
        row = {"id": mine["id"], "name": p["name"], "start_date": _iso_mdy(p.get("start_date")),
               "target_date": _iso_mdy(p.get("end_date"))}
        lead = people.get((p.get("owner_name") or "").lower())
        if lead:
            row["lead_id"] = lead
        if p.get("status") == "completed":
            row["status"] = "done"
        out["projects"].append(row)

    for zid, payload in raw["list_tasks"].items():
        if zid not in by_zoho:
            continue
        for t in payload.get("tasks", []):
            owners = (t.get("details") or {}).get("owners") or []
            who = people.get(owners[0]["name"].lower()) if owners else None
            if owners and not who:
                warnings.append(f"{t['key']}: owner {owners[0]['name']!r} is not a person in Neura1")
            status = TASK_STATUS.get(str((t.get("status") or {}).get("name", "")).lower())
            if not status:
                warnings.append(f"{t['key']}: unknown status {t.get('status')!r}, left as it was")
            row = {"id": t["key"], "title": t["name"], "project_id": by_zoho[zid],
                   "created": _iso_mdy(t.get("created_time")), "start": _iso_mdy(t.get("start_date")),
                   "due": _iso_mdy(t.get("end_date")), "completed": _iso_mdy(t.get("completed_time"))}
            if who:
                row["assignee_id"] = who
            if status:
                row["status"] = status
            out["tasks"].append(row)
    return out, warnings


def _num(v) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:.2f}".rstrip("0")


# ---------- diff against the graph ----------

CURRENT = {
    "stock": "MATCH (i:Item) WHERE i.on_hand IS NOT NULL RETURN i.id AS item_id, i.on_hand AS on_hand, i.allocated AS allocated",
    "purchase_orders": """
        MATCH (po:PurchaseOrder)-[:FROM_SUPPLIER]->(s:Supplier), (po)-[:ORDERS]->(i:Item)
        OPTIONAL MATCH (po)-[:PRICED_BY]->(q:Quote)
        RETURN po.id AS id, s.id AS supplier_id, i.id AS item_id, po.qty AS qty, po.unit_price AS unit_price,
               po.currency AS currency, po.ordered_on AS ordered_on, po.expected_on AS expected_on, po.status AS status,
               q.id AS quote_id""",
    "receipts": """
        MATCH (g:Receipt)-[:AGAINST]->(po:PurchaseOrder), (g)-[:RECEIVES]->(i:Item)
        RETURN g.id AS id, po.id AS po_id, i.id AS item_id, g.qty AS qty, g.received_on AS received_on,
               g.location AS location, g.lot AS lot, g.rejected AS rejected, g.note AS note""",
    "stock_moves": "MATCH (m:StockMove)-[:MOVES]->(i:Item) RETURN m.id AS id, i.id AS item_id",
    "projects": """
        MATCH (p:Project) OPTIONAL MATCH (lead:Person)-[:LEADS]->(p)
        RETURN p.id AS id, p.name AS name, p.status AS status, lead.id AS lead_id, p.start_date AS start_date,
               p.target_date AS target_date, p.summary AS summary""",
    "tasks": """
        MATCH (a:Action {kind:'work'})
        OPTIONAL MATCH (a)-[:ASSIGNED_TO]->(who:Person) OPTIONAL MATCH (a)-[:IN_PROJECT]->(p:Project)
        RETURN a.id AS id, a.title AS title, who.id AS assignee_id, p.id AS project_id, a.target AS target_id,
               a.status AS status, a.created_at AS created, a.completed_at AS completed, a.start_date AS start,
               a.due_date AS due""",
}

LABEL = {"stock": "Stock", "purchase_orders": "Purchase order", "receipts": "Goods received", "stock_moves": "Stock movement",
         "projects": "Project", "tasks": "Task"}


def _norm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    s = str(v).strip()
    try:
        f = float(s)
    except ValueError:
        return s
    if not s[:1].isdigit() and s[:1] != "-" or f != f or f in (float("inf"), float("-inf")):
        return s
    return str(int(f)) if f.is_integer() else repr(f)  # 6.50 and 6.5 are the same price


def diff(graph: Graph, incoming: dict[str, list[dict]]) -> list[dict]:
    """Field-by-field changes; each change carries the complete row to load."""
    changes = []
    for kind in KINDS:
        key = SPECS[kind].key or "id"
        current = {r[key]: r for r in rows(graph, CURRENT[kind])}
        for row in incoming.get(kind, []):
            before = current.get(row[key])
            full = {c: _norm((before or {}).get(c)) for c in SPECS[kind].columns} | {k: _norm(v) for k, v in row.items()}
            if before is None:
                if kind == "receipts" and not full["rejected"]:
                    full["rejected"] = "0"
                changes.append({"kind": kind, "id": row[key], "change": "new", "fields": {}, "row": full})
                continue
            fields = {c: [_norm(before.get(c)), full[c]] for c in row if c in SPECS[kind].columns
                      and _norm(before.get(c)) != full[c]}
            if fields:
                changes.append({"kind": kind, "id": row[key], "change": "updated", "fields": fields, "row": full})
    # A new goods-received note moves stock: record the movement too, as the ERP's own ledger does.
    have_moves = {r["id"] for r in rows(graph, CURRENT["stock_moves"])}
    for c in [c for c in changes if c["kind"] == "receipts" and c["change"] == "new"]:
        r = c["row"]
        mid = f"SM-{r['id']}"
        if mid not in have_moves:
            changes.append({"kind": "stock_moves", "id": mid, "change": "new", "fields": {}, "row": {
                "id": mid, "item_id": r["item_id"], "date": r["received_on"], "qty": r["qty"], "kind": "receipt",
                "ref": r["id"], "location": r["location"], "note": f"Received against {r['po_id']}"}})
    return changes


def _csv(kind: str, data: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, SPECS[kind].columns, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(data)
    return buf.getvalue()


def summary(c: dict) -> str:
    what = f"{LABEL[c['kind']]} {c['id']}"
    if c["change"] == "new":
        r = c["row"]
        extra = {"tasks": lambda: f": {r['title']}", "receipts": lambda: f": {r['qty']} × {r['item_id']} against {r['po_id']}",
                 "stock_moves": lambda: f": {r['qty']} × {r['item_id']} into stores"}.get(c["kind"], lambda: "")()
        return f"New {what[0].lower() + what[1:]}{extra}"
    parts = [f"{k.replace('_', ' ')} {a or '(empty)'} → {b or '(empty)'}" for k, (a, b) in c["fields"].items()]
    return f"{what}: {'; '.join(parts)}"


# ---------- run ----------

def run(graph: Graph, dry_run: bool = False, server=None, by: str | None = None) -> dict:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        raw = fetch(server)
    except Exception as exc:
        return {"ok": False, "stage": "fetch", "error": f"Could not read the source over MCP: {exc}"}
    incoming, warnings = to_records(raw, graph)
    changes = diff(graph, incoming)
    report = {"ok": True, "dry_run": dry_run, "at": started, "source": describe(), "tools": raw["tools"],
              "read": {k: len(v) for k, v in incoming.items()}, "warnings": warnings,
              "changes": [{k: v for k, v in c.items() if k != "row"} | {"summary": summary(c)} for c in changes]}
    if not changes:
        report["message"] = "Already up to date: Zoho and Neura1 agree on every record read."
    if dry_run or not changes:
        return report
    by_kind = {k: [c["row"] for c in changes if c["kind"] == k] for k in ORDER if any(c["kind"] == k for c in changes)}
    check = validate({f"{k}.csv": _csv(k, v) for k, v in by_kind.items()}, existing_ids(graph))
    if not check["ok"]:
        check.pop("_parsed", None)
        return report | {"ok": False, "stage": "validate", "validation": check,
                         "error": "The source's records failed validation; nothing was written."}
    for kind in ORDER:
        if kind in check["_parsed"]:
            load_rows(graph, kind, check["_parsed"][kind], f"erp/zoho/{kind}")
    run_id = f"SYNC-{uuid.uuid4().hex[:8]}"
    graph.query("""
        CREATE (r:SyncRun {id:$id, connector:'zoho', at:$at, by:$by, simulated:$sim, changes:$n, summary:$summary})
        WITH r UNWIND $items AS c
        CREATE (x:SyncChange {id:$id + ':' + toString(c.n), connector:'Zoho', at:$at, what:c.what, detail:c.detail,
                              ref:c.ref, kind:c.kind})
        CREATE (x)-[:IN_RUN]->(r)
        WITH x, c OPTIONAL MATCH (t {id:c.ref}) WHERE NOT t:SyncChange
        FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | MERGE (x)-[:ABOUT]->(t))""",
                {"id": run_id, "at": started, "by": by, "sim": not settings.erp_mcp_url, "n": len(changes),
                 "summary": json.dumps(report["changes"]),
                 "items": [{"n": n, "what": f"Synced from Zoho: {LABEL[c['kind']].lower()} {c['id']}",
                            "detail": summary(c), "ref": c["id"], "kind": c["kind"]} for n, c in enumerate(changes)]})
    return report | {"run": run_id, "message": f"{len(changes)} change{'s' if len(changes) != 1 else ''} synced from Zoho."}


def history(graph: Graph, limit: int = 10) -> list[dict]:
    out = rows(graph, "MATCH (r:SyncRun) RETURN r.id AS id, r.at AS at, r.by AS by, r.simulated AS simulated, "
                      "r.changes AS changes, r.summary AS summary ORDER BY r.at DESC LIMIT $n", {"n": limit})
    for r in out:
        r["changes_list"] = json.loads(r.pop("summary") or "[]")
    return out
