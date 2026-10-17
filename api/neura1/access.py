"""Who may see what, derived from the graph rather than from a separate permission table.

The viewer is a Person (sent as the X-Neura1-As header by the web app). Rules:
  * Money (order values, prices, penalties, cost changes): leadership, the board, business development,
    purchase and project management.
  * Leave details (dates and notes): the person themself, anyone above them in the reporting chain, their backup,
    HR, and leadership. Everyone else only sees whether the person is away today.
With no viewer (internal calls, tests, MCP) everything is visible; the web app always sends a viewer.
"""

import re
from dataclasses import dataclass, field

from falkordb import Graph

from neura1.graph import rows

MONEY_TEAMS = {"T-LEAD", "T-SALES", "T-SC"}
LEAVE_TEAMS = {"T-LEAD", "T-HR"}

VIEWER = """
MATCH (p:Person {id:$id})
OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (r:Person)-[:REPORTS_TO*1..6]->(p)
OPTIONAL MATCH (p)-[:BACKS_UP]->(covered:Person)
RETURN p.id AS id, p.name AS name, p.role AS role, t.id AS team, t.name AS team_name,
       collect(DISTINCT r.id) AS reports, collect(DISTINCT covered.id) AS covers
"""


@dataclass
class Viewer:
    id: str | None = None
    name: str = "Everyone"
    role: str = ""
    team: str | None = None
    team_name: str | None = None
    reports: set = field(default_factory=set)
    covers: set = field(default_factory=set)

    @property
    def unrestricted(self) -> bool:
        return self.id is None

    @property
    def sees_money(self) -> bool:
        return self.unrestricted or self.team in MONEY_TEAMS

    def sees_leave_of(self, person_id: str) -> bool:
        return (self.unrestricted or person_id == self.id or person_id in self.reports
                or person_id in self.covers or self.team in LEAVE_TEAMS)

    def sees_profile_of(self, person_id: str) -> bool:
        """A person's expertise from their work: themselves, their management chain, HR and leadership."""
        return (self.unrestricted or person_id == self.id or person_id in self.reports
                or self.team in LEAVE_TEAMS)

    def describe(self) -> dict:
        return {"id": self.id, "name": self.name, "role": self.role, "team": self.team_name,
                "sees_money": self.sees_money, "reports": sorted(self.reports),
                "leave_visible_for": "everyone" if self.unrestricted or self.team in LEAVE_TEAMS
                else "self, reports and people they back up"}


def viewer(graph: Graph, person_id: str | None) -> Viewer:
    if not person_id:
        return Viewer()
    found = rows(graph, VIEWER, {"id": person_id})
    if not found:
        return Viewer()
    v = found[0]
    return Viewer(v["id"], v["name"], v["role"], v["team"], v["team_name"], set(v["reports"]), set(v["covers"]))


RESTRICTED = {"restricted": True}


MONEY_TEXT = re.compile(r"(₹|\bINR\s?|\bRs\.?\s?)\s?\d[\d,]*(\.\d+)?( lakh| crore)?", re.I)


def redact_money_text(obj, note: str = "[amount hidden]"):
    """Hide rupee amounts written inside any text (messages, answers, quotes) for people who may not see money."""
    if isinstance(obj, str):
        return MONEY_TEXT.sub(note, obj)
    if isinstance(obj, dict):
        return {k: redact_money_text(v, note) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_money_text(x, note) for x in obj]
    return obj


def redact_money(obj, keys=("value", "unit_price", "max_penalty", "open_value", "value_at_risk", "total_delta",
                            "material_delta", "one_time_total", "baseline_unit_price", "new_unit_price",
                            "cost_total", "amount")):
    """Replace money fields anywhere in a response with None and mark the response."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[k] = None if k in keys and isinstance(v, (int, float, str)) and v not in ("", None) else redact_money(v, keys)
        return out
    if isinstance(obj, list):
        return [redact_money(x, keys) for x in obj]
    return obj
