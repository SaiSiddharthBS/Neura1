"""Neura1 for agents in the cloud: OpenAI Dots, ChatGPT, Claude, or any MCP client, over Streamable HTTP.

Dots and ChatGPT plugins reach outside tools through remote MCP servers. This one is served by the Neura1 API at
/api/agent/mcp (so it travels through the same proxy and tunnel as the app), and it is OFF unless
NEURA1_AGENT_MCP_TOKEN is set. Callers authenticate with "Authorization: Bearer <token>", or, for clients that can
only take a URL, with the token as a path segment: /api/agent/<token>/mcp.

What an agent may see is decided exactly as for a person: it reads as NEURA1_AGENT_VIEWER (a person id), with that
person's permissions. Unset, it is an "external agent" that sees no amounts and nobody's leave. Every tool is
read-only, and the raw Cypher tool of the local MCP server is not offered here, so nothing can step around those
permissions. Turning this on sends answers to the agent's provider; leave it off to keep everything on premises.
"""

import hmac
import json
from datetime import date

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from neura1 import access
from neura1.agent import _restrict, run_tool
from neura1.config import settings
from neura1.graph import get_graph
from neura1.impact import Trace

mcp = MCPServer("neura1", instructions=(
    "Neura1 is a company brain for hardware manufacturers; this server holds Flyvi Technologies (synthetic demo "
    "data). Use it to find what a supplier change breaks, which builds, orders and projects are slipping and why, "
    "whether a delivery date can be promised, who knows what, and what changed. Answers are permission-filtered: "
    "amounts and leave plans may be hidden. Alternates are not approved unless a decision says so."))


def agent_viewer(graph) -> access.Viewer:
    if settings.agent_viewer:
        v = access.viewer(graph, settings.agent_viewer)
        if v.id:
            return v
    return access.Viewer(id="agent", name="External agent")


def _call(tool: str, **args) -> str:
    graph = get_graph()
    v = agent_viewer(graph)
    restrict = {"money": v.sees_money, "leave_of": v.sees_leave_of, "hidden": access.hidden_sources(graph, v.sees_leave_of)}
    try:
        result = _restrict(tool, run_tool(graph, Trace(graph), tool, {k: x for k, x in args.items() if x is not None}),
                           restrict)
    except Exception as exc:  # report the reason to the calling agent instead of failing the call
        return json.dumps({"error": str(exc)})
    if not v.sees_money:
        result = access.redact_money_text(access.redact_money(result))
    return json.dumps({"result": result, "read_as": v.name}, default=str)[:20000]


@mcp.tool()
def change_impact(item_id: str, new_unit_price: float | None = None, lead_weeks: int | None = None) -> str:
    """What a supplier change to a part breaks: revisions, builds, customer orders, people, decisions and actions."""
    return _call("change_impact", item_id=item_id, new_unit_price=new_unit_price, lead_weeks=lead_weeks)


@mcp.tool()
def timeline_deviations() -> str:
    """Which projects, builds, customer orders and tasks are slipping against the plan, by how many days, and why."""
    from neura1 import timeline
    graph = get_graph()
    v = agent_viewer(graph)
    t = timeline.timeline(graph, v)
    late = [{"id": i["id"], "kind": i["kind"], "title": i["title"], "owner": i["owner"], "state": i["state"],
             "plan_end": i["plan"]["end"], "forecast_end": i["forecast"]["end"], "deviation_days": i["deviation_days"],
             "why": i["reasons"]}
            for g in t["groups"] for i in g["items"] if i["state"] in ("late", "at_risk", "unconfirmed")]
    projects = [{"id": g["id"], "name": g["name"], "target": g["plan"]["end"], "forecast": g["forecast"]["end"],
                 "deviation_days": g["deviation_days"], "why": g["reasons"]} for g in t["groups"] if g["plan"]["end"]]
    out = {"today": t["today"], "summary": t["summary"], "projects": projects, "slipping": late, "rules": t["rules"],
           "read_as": v.name}
    if not v.sees_money:
        out = access.redact_money_text(access.redact_money(out))
    return json.dumps(out, default=str)[:20000]


@mcp.tool()
def can_we_promise(product: str, qty: int, due: str) -> str:
    """Whether a quantity of a product can be delivered by a date (YYYY-MM-DD): parts, notices, people, certificates."""
    date.fromisoformat(due)
    return _call("can_we_promise", product=product, qty=qty, due=due)


@mcp.tool()
def where_used(item_id: str) -> str:
    """Which product revisions use a part, quantity per unit, and which revisions are excluded and why."""
    return _call("where_used", item_id=item_id)


@mcp.tool()
def who_knows(text: str) -> str:
    """Who knows most about a part, product, customer or topic, from the work and conversations on record."""
    return _call("who_knows", text=text)


@mcp.tool()
def project(text: str) -> str:
    """A project: lead, members, scope, tasks and their status."""
    return _call("project", text=text)


@mcp.tool()
def list_projects() -> str:
    """All projects with their lead, status and target date."""
    return _call("list_projects")


@mcp.tool()
def customer(text: str) -> str:
    """A customer: open orders, the builds behind them, who looks after the account, and open issues."""
    return _call("customer", text=text)


@mcp.tool()
def decisions(item_id: str) -> str:
    """Decisions recorded about a part or product, each with its verbatim evidence."""
    return _call("decisions", item_id=item_id)


@mcp.tool()
def alternates(item_id: str) -> str:
    """Alternate parts for a part and whether each is approved, rejected or not qualified, with the decisions."""
    return _call("alternates", item_id=item_id)


@mcp.tool()
def inventory(item_id: str | None = None) -> str:
    """Stock: what needs ordering, or one part's stock, open orders, receipts and usage."""
    return _call("inventory", item_id=item_id)


@mcp.tool()
def search_documents(query: str) -> str:
    """Search chats, tickets, reports, notices and meetings by meaning and keywords; returns passages with sources."""
    return _call("search_documents", query=query)


@mcp.tool()
def recent_changes() -> str:
    """What changed recently: messages, decisions, documents, task updates and syncs from the ERP."""
    return _call("recent_changes")


@mcp.tool()
def risk_radar() -> str:
    """Where the company is fragile: chokepoints, single-sourced parts, and knowledge held by one person."""
    return _call("risk_radar")


# ---------- HTTP: a token gate in front of the MCP app ----------

http_app = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                   transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


class Gate:
    """Off unless a token is set; then a matching bearer token, or the token as the first path segment."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        token = settings.agent_mcp_token
        path = scope.get("path", "")
        if token:
            sent = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
            if sent.startswith("Bearer ") and hmac.compare_digest(sent[7:], token):
                return await self.app(scope, receive, send)
            sub = scope.get("root_path", "")
            rel = path[len(sub):] if sub and path.startswith(sub) else path
            if rel.startswith("/") and "/" in rel[1:] and hmac.compare_digest(rel[1:].split("/", 1)[0], token):
                rest = "/" + rel[1:].split("/", 1)[1]
                return await self.app(scope | {"path": (sub + rest) if sub and path.startswith(sub) else rest,
                                               "raw_path": ((sub + rest) if sub and path.startswith(sub) else rest).encode()},
                                      receive, send)
        status, body = (404, b'{"detail":"Agent access is off. Set NEURA1_AGENT_MCP_TOKEN to turn it on."}') if not token \
            else (401, b'{"detail":"A valid agent token is required"}')
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
        await send({"type": "http.response.body", "body": body})


gated_app = Gate(http_app)
