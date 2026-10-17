"""Who may see what, derived from the graph rather than from a separate permission table.

The viewer is a Person (sent as the X-Neura1-As header by the web app). Rules:
  * Money (order values, prices, penalties, cost changes): the directors and the leadership team.
  * Leave details (dates and notes): the person themself, their backup, and the directors and leadership team.
    Everyone else only sees whether the person is away today.
Flyvi has three tiers: directors, leadership, and employees. Any reporting lines recorded in the graph also apply.
With no viewer (internal calls, tests, MCP) everything is visible; the web app always sends a viewer.
"""

import re
from dataclasses import dataclass, field

from falkordb import Graph

from neura1.graph import rows

LEADERSHIP = {"T-DIR", "T-LEAD"}   # directors, and the leadership team under them
MONEY_TEAMS = LEADERSHIP
LEAVE_TEAMS = LEADERSHIP

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
    def leader(self) -> bool:
        return self.team in LEADERSHIP

    @property
    def sees_money(self) -> bool:
        return self.unrestricted or self.team in MONEY_TEAMS

    def sees_leave_of(self, person_id: str) -> bool:
        return (self.unrestricted or person_id == self.id or person_id in self.reports
                or person_id in self.covers or self.team in LEAVE_TEAMS)

    def sees_profile_of(self, person_id: str) -> bool:
        """A person's expertise from their work: themselves, anyone they manage, and the directors and leadership."""
        return (self.unrestricted or person_id == self.id or person_id in self.reports
                or self.team in LEAVE_TEAMS)

    def describe(self) -> dict:
        return {"id": self.id, "name": self.name, "role": self.role, "team": self.team_name,
                "sees_money": self.sees_money, "reports": sorted(self.reports),
                "leave_visible_for": "everyone" if self.unrestricted or self.team in LEAVE_TEAMS
                else "self and people they back up"}


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


def hidden_sources(graph: Graph, sees_leave_of) -> set[str]:
    """Leave notices whose person this reader may not see the leave of. Their passages must not reach the reader
    through search, evidence, feeds or the agent."""
    from neura1 import scenarios
    return {s["id"] for s in scenarios.signals(graph) if s["kind"] == "leave" and not sees_leave_of(s.get("subject") or "")}


_REF_KEYS = ("chunk", "ref", "id", "source", "source_id")


def _is_hidden(value, hidden: set[str]) -> bool:
    return isinstance(value, str) and (value in hidden or value.split("#")[0] in hidden)


def drop_hidden(obj, hidden: set[str]):
    """Remove every list entry that is, or points at, a hidden source or one of its passages."""
    if not hidden:
        return obj
    if isinstance(obj, list):
        out = []
        for x in obj:
            if _is_hidden(x, hidden) or (isinstance(x, dict) and any(_is_hidden(x.get(k), hidden) for k in _REF_KEYS)):
                continue
            out.append(drop_hidden(x, hidden))
        return out
    if isinstance(obj, dict):
        return {k: drop_hidden(v, hidden) for k, v in obj.items()}
    return obj


def points_at_hidden(obj, hidden: set[str]) -> bool:
    return isinstance(obj, dict) and any(_is_hidden(obj.get(k), hidden) for k in _REF_KEYS)


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
