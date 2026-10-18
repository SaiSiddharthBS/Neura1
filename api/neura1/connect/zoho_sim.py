"""A simulated Zoho Inventory + Zoho Projects, served over MCP, for the demo.

Flyvi runs Zoho. Zoho's own MCP service (mcp.zoho.com) lets an agent read Zoho Inventory and Zoho Projects; this
server stands in for it so the demo never touches real company data. It serves the synthetic Flyvi records in the
shapes Zoho's REST APIs use (field names such as purchaseorder_number, stock_on_hand, line_items, details.owners and
MM-DD-YYYY dates in Zoho Projects), plus the changes in fixture/<company>/erp/zoho_changes.json, as if someone had
been working in Zoho since the last export.

  uv run python -m neura1.connect.zoho_sim        # stdio transport; Neura1 Connect launches it by itself

Everything here is read-only and synthetic.
"""

import hashlib
import json
from datetime import date

from mcp.server.mcpserver import MCPServer

from neura1.config import settings
from neura1.ingest.structured import read_csv

mcp = MCPServer("zoho-simulated", instructions=(
    "A simulated Zoho Inventory and Zoho Projects for Flyvi Technologies (synthetic data). Read-only. Shapes follow "
    "Zoho's REST APIs: Inventory dates are YYYY-MM-DD, Projects dates are MM-DD-YYYY."))

ORG_ID = "60012345678"


def _records(name: str) -> list[dict]:
    return read_csv(settings.fixture_dir / "records" / f"{name}.csv")


def _changes() -> dict:
    path = settings.fixture_dir / "erp" / "zoho_changes.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _zid(prefix: int, text: str) -> str:
    """A stable Zoho-style numeric id for a record."""
    return str(prefix * 10**12 + int(hashlib.sha256(text.encode()).hexdigest()[:12], 16) % 10**12)


def _mdy(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d.month:02d}-{d.day:02d}-{d.year}"


@mcp.tool()
def list_items() -> str:
    """Zoho Inventory: GET /items. Every item with its SKU and stock on hand."""
    stock = {r["item_id"]: r for r in _records("stock")}
    details = {r["item_id"]: r for r in _records("item_details")}
    edits = _changes().get("inventory", {}).get("items", {})
    out = []
    for i in _records("items"):
        if i["id"] not in stock:
            continue
        on_hand = int(stock[i["id"]]["on_hand"])
        row = {"item_id": _zid(46, i["id"]), "name": i["name"], "sku": i["id"], "part_number": i.get("mpn", ""),
               "manufacturer": i.get("manufacturer", ""), "unit": (details.get(i["id"]) or {}).get("uom") or "pcs",
               "status": "active", "stock_on_hand": on_hand}
        row |= edits.get(i["id"], {})
        out.append(row)
    return json.dumps({"code": 0, "message": "success", "items": out,
                       "page_context": {"page": 1, "per_page": 200, "has_more_page": False}})


@mcp.tool()
def list_purchase_orders() -> str:
    """Zoho Inventory: GET /purchaseorders. Purchase orders with their line items."""
    suppliers = {r["id"]: r["name"] for r in _records("suppliers")}
    edits = _changes().get("inventory", {}).get("purchase_orders", {})
    received: dict[str, int] = {}
    for g in _records("receipts"):
        received[g["po_id"]] = received.get(g["po_id"], 0) + int(g["qty"])
    for g in _changes().get("inventory", {}).get("purchase_receives", []):
        received[g["purchaseorder_number"]] = received.get(g["purchaseorder_number"], 0) + sum(
            int(li["quantity"]) for li in g["line_items"])
    out = []
    for po in _records("purchase_orders"):
        row = {"purchaseorder_id": _zid(47, po["id"]), "purchaseorder_number": po["id"],
               "vendor_id": _zid(48, po["supplier_id"]), "vendor_name": suppliers[po["supplier_id"]],
               "date": po["ordered_on"], "delivery_date": po["expected_on"], "status": po["status"],
               "currency_code": po["currency"] or "INR", "reference_number": po.get("quote_id", ""),
               "line_items": [{"item_id": _zid(46, po["item_id"]), "sku": po["item_id"], "quantity": int(po["qty"]),
                               "purchase_rate": float(po["unit_price"]), "quantity_received": received.get(po["id"], 0)}]}
        row |= edits.get(po["id"], {})
        out.append(row)
    return json.dumps({"code": 0, "message": "success", "purchaseorders": out,
                       "page_context": {"page": 1, "per_page": 200, "has_more_page": False}})


@mcp.tool()
def list_purchase_receives() -> str:
    """Zoho Inventory: GET /purchasereceives. Goods received against purchase orders."""
    out = [{"receive_id": _zid(49, g["id"]), "receive_number": g["id"], "purchaseorder_id": _zid(47, g["po_id"]),
            "purchaseorder_number": g["po_id"], "date": g["received_on"], "location_name": g.get("location", ""),
            "notes": g.get("note", ""), "line_items": [{"item_id": _zid(46, g["item_id"]), "sku": g["item_id"],
                                                         "quantity": int(g["qty"])}]}
           for g in _records("receipts")]
    for g in _changes().get("inventory", {}).get("purchase_receives", []):
        out.append({"receive_id": _zid(49, g["receive_number"]), "purchaseorder_id": _zid(47, g["purchaseorder_number"]),
                    **g, "line_items": [li | {"item_id": _zid(46, li["sku"])} for li in g["line_items"]]})
    return json.dumps({"code": 0, "message": "success", "purchasereceives": out,
                       "page_context": {"page": 1, "per_page": 200, "has_more_page": False}})


STATUS_OUT = {"open": "Open", "in_progress": "In Progress", "blocked": "On Hold", "done": "Closed"}


@mcp.tool()
def list_projects() -> str:
    """Zoho Projects: GET /restapi/portal/{portal}/projects/. Projects, plus "General" for work outside one."""
    people = {r["id"]: r["name"] for r in _records("people")}
    out = [{"id": _zid(17, p["id"]), "name": p["name"], "status": "active" if p["status"] != "done" else "completed",
            "start_date": _mdy(p["start_date"]), "end_date": _mdy(p["target_date"]),
            "owner_name": people.get(p["lead_id"], ""), "description": p.get("summary", "")}
           for p in _records("projects")]
    out.append({"id": _zid(17, "GENERAL"), "name": "General", "status": "active", "start_date": "", "end_date": "",
                "owner_name": "", "description": "Work that is not part of a project"})
    return json.dumps({"projects": out})


@mcp.tool()
def list_tasks(project_id: str) -> str:
    """Zoho Projects: GET /restapi/portal/{portal}/projects/{project_id}/tasks/. A project's tasks."""
    people = {r["id"]: r["name"] for r in _records("people")}
    projects = {_zid(17, p["id"]): p for p in _records("projects")}
    names = {_zid(17, p["id"]): p["name"] for p in _records("projects")} | {_zid(17, "GENERAL"): "General"}
    if project_id not in names:
        return json.dumps({"error": {"code": 6404, "message": "Project not found"}})
    edits = _changes().get("projects", {})
    out = []
    for t in _records("tasks"):
        in_project = (projects.get(project_id) or {}).get("id") == t["project_id"] or (
            names[project_id] == "General" and not t["project_id"])
        if not in_project:
            continue
        row = {"id": _zid(18, t["id"]), "key": t["id"], "name": t["title"],
               "status": {"name": STATUS_OUT[t["status"]]}, "completed": t["status"] == "done",
               "percent_complete": "100" if t["status"] == "done" else "0",
               "created_time": _mdy(t["created"]), "start_date": _mdy(t.get("start")), "end_date": _mdy(t.get("due")),
               "completed_time": _mdy(t.get("completed")),
               "details": {"owners": [{"name": people[t["assignee_id"]], "id": _zid(19, t["assignee_id"])}]
                           if t["assignee_id"] else []},
               "tasklist": {"name": "General", "id": _zid(20, t["project_id"] or "GENERAL")}}
        change = (edits.get("tasks") or {}).get(t["id"], {})
        if "status" in change:
            change = change | {"status": {"name": change["status"]}}
        out.append(row | change)
    for n in edits.get("new_tasks", []):
        if n["project"] != names[project_id]:
            continue
        out.append({"id": _zid(18, n["key"]), "key": n["key"], "name": n["name"], "status": {"name": n["status"]},
                    "completed": n["status"] == "Closed", "percent_complete": "0", "created_time": n["created_time"],
                    "start_date": n["start_date"], "end_date": n["end_date"], "completed_time": "",
                    "details": {"owners": [{"name": n["owner"], "id": _zid(19, n["owner"])}]},
                    "tasklist": {"name": "General", "id": _zid(20, n["project"])}})
    return json.dumps({"tasks": out})


if __name__ == "__main__":
    mcp.run()
