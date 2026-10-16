"""Neura1 as an MCP server: the company graph's tools for any MCP client (Claude Desktop, IDEs, other agents).

  uv run python -m neura1.mcp_server        # stdio transport

Every tool is read-only. Task creation stays a human step in the Neura1 app, so an external
agent can only draft tasks.
"""

import json

from mcp.server.mcpserver import MCPServer

from neura1.agent import run_tool
from neura1.graph import get_graph
from neura1.impact import Trace

mcp = MCPServer("neura1", instructions=(
    "Neura1 is the company brain of Flyvi Technologies (power electronics for aerospace and defence; synthetic demo data), stored in FalkorDB. Use these tools to "
    "trace part changes, find who owns and who knows what, look up projects and decisions with their sources, "
    "and see what changed. Alternates are not approved unless a decision says so."))


def _call(tool: str, **args) -> str:
    graph = get_graph()
    trace = Trace(graph)
    try:
        result = run_tool(graph, trace, tool, {k: v for k, v in args.items() if v is not None})
    except Exception as exc:  # report the reason to the calling agent instead of crashing the tool
        return json.dumps({"error": str(exc)})
    return json.dumps({"result": result, "cypher": [s["cypher"] for s in trace.steps]}, default=str)[:20000]


@mcp.tool()
def where_used(item_id: str) -> str:
    """Which product revisions use a part, quantity per unit, and which revisions are excluded and why."""
    return _call("where_used", item_id=item_id)


@mcp.tool()
def change_impact(item_id: str, new_unit_price: float | None = None, lead_weeks: int | None = None) -> str:
    """Full impact of a price or lead-time change: builds, orders, customers, dependencies, alternates, cost, tasks."""
    return _call("change_impact", item_id=item_id, new_unit_price=new_unit_price, lead_weeks=lead_weeks)


@mcp.tool()
def who_knows(text: str) -> str:
    """Who knows about a part, project, customer or alias, ranked with the reasons and evidence."""
    return _call("who_knows", text=text)


@mcp.tool()
def person(name: str) -> str:
    """A person's role, team, backup, what they own, projects, decisions, open tasks and topics."""
    return _call("person", name=name)


@mcp.tool()
def project(text: str) -> str:
    """A project's lead, members, scope, related decisions, open tasks and recent discussion."""
    return _call("project", text=text)


@mcp.tool()
def list_projects() -> str:
    """All projects with status, lead and target date."""
    return _call("list_projects")


@mcp.tool()
def decisions(item_id: str) -> str:
    """Recorded decisions about a part or its alternates, with who decided and verbatim source quotes."""
    return _call("decisions", item_id=item_id)


@mcp.tool()
def alternates(item_id: str) -> str:
    """Alternate parts with quotes and approval status (a cross-reference or bench test is not an approval)."""
    return _call("alternates", item_id=item_id)


@mcp.tool()
def search_documents(query: str) -> str:
    """Full-text search over chats, tickets, reports and notices."""
    return _call("search_documents", query=query)


@mcp.tool()
def recent_changes() -> str:
    """Recent activity, plus knowledge that may be out of date."""
    return _call("recent_changes")


@mcp.tool()
def read_only_cypher(query: str) -> str:
    """Run a read-only Cypher query on the company graph (writes are blocked, LIMIT enforced)."""
    return _call("read_only_cypher", query=query)


@mcp.tool()
def absence_impact(name: str) -> str:
    """What happens if a person is away: ownership, open tasks, knowledge only they hold, handover plan."""
    return _call("absence_impact", name=name)


@mcp.tool()
def customer(text: str) -> str:
    """A customer's orders, value, penalties, field units, tickets, escalations and escalation plan."""
    return _call("customer", text=text)


@mcp.tool()
def risk_radar() -> str:
    """Where the company is fragile: chokepoints, single-sourced parts, one-person knowledge, concentration."""
    return _call("risk_radar")


@mcp.tool()
def recall(text: str) -> str:
    """What people have already asked and been told about a record or topic (shared conversation memory)."""
    return _call("recall", text=text)


@mcp.tool()
def propose_task(owner: str, title: str, why: str, target: str | None = None) -> str:
    """Draft a task for a person. It is not created until someone confirms it in Neura1."""
    return _call("propose_task", owner=owner, title=title, why=why, target=target)


if __name__ == "__main__":
    mcp.run()
