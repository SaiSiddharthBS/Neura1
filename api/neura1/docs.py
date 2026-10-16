"""Generate docs/queries.md from neura1/queries.py: `uv run python -m neura1.docs`."""

import ast
import re

from neura1.config import REPO_ROOT

USED_BY = {
    "WHERE_USED": "Impact workspace (graph, Engineering tab), cost scenario",
    "RESOLVE_ITEM": "Every analysis: notice part number → internal item",
    "EXPOSURE": "Production and Sales tabs, builds-at-risk, customer tasks",
    "FIELD_UNITS": "Support tab",
    "DEPENDENTS": "Engineering tab, firmware and requalification tasks",
    "DIRECT_PARENTS": "Engineering change review tasks",
    "QUOTES": "Procurement tab, cost baseline",
    "ALTERNATES": "Alternate banners",
    "DECISIONS": "Rejected/pending alternate banners, decision nodes in the graph",
    "EVIDENCE_FOR": "Evidence lookups",
    "POLICY_CHUNK": "Task citations",
    "SEARCH_PASSAGES": "Company brain search",
    "SUGGEST_ITEMS": "Unresolved part numbers in notices (suggestions, never auto-picked)",
    "RESOLVE_ANY": "Who knows · Ask agent · MCP: name, id or chat alias → record",
    "WHO_KNOWS": "Who knows about… (Company brain), Ask and MCP `who_knows`",
    "PERSON": "People page", "PERSON_OWNS": "People page", "PERSON_PROJECTS": "People page",
    "PERSON_DECISIONS": "People page", "PERSON_TASKS": "People page", "PERSON_TOPICS": "People page · what they know",
    "PERSON_RECENT": "People page", "PEOPLE": "People directory", "PROJECTS": "Projects page",
    "PROJECT": "Project detail", "PROJECT_MEMBERS": "Project detail", "PROJECT_SCOPE": "Project detail",
    "PROJECT_DECISIONS": "Project detail", "PROJECT_TASKS": "Project detail", "PROJECT_ACTIVITY": "Project detail",
    "CHANGES": "What's new feed", "STALE_EVIDENCE": "What's new · needs attention",
    "STALE_DECISIONS": "What's new · needs attention", "EXPIRING_QUOTES": "What's new · needs attention",
    "UNOWNED": "What's new · needs attention",
}


def main() -> None:
    out = ["# Cypher queries Neura1 depends on", "",
           "Generated from [`queries.py`](../api/neura1/queries.py), [`brain.py`](../api/neura1/brain.py) and "
           "[`scenarios.py`](../api/neura1/scenarios.py) by `uv run python -m neura1.docs`.",
           "All queries are parameterised and run read-only (`GRAPH.RO_QUERY`). Writes happen only in the loaders",
           "(`api/neura1/ingest/`) and in `api/neura1/actions.py`.", ""]
    for module in ("queries.py", "brain.py", "scenarios.py"):
        src = (REPO_ROOT / "api" / "neura1" / module).read_text()
        out += _section(src, {"queries.py": "Change impact", "brain.py": "The wider company brain",
                              "scenarios.py": "Company events and the risk radar"}[module])
    (REPO_ROOT / "docs").mkdir(exist_ok=True)
    (REPO_ROOT / "docs" / "queries.md").write_text("\n".join(out))
    print("wrote docs/queries.md")


def _section(src: str, heading: str) -> list[str]:
    lines = src.splitlines()
    out = [f"# {heading}", ""]
    for node in ast.parse(src).body:
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)):
            continue
        name = node.targets[0].id
        comment = []
        i = node.lineno - 2
        while i >= 0 and lines[i].startswith("#"):
            comment.insert(0, lines[i].lstrip("# ").rstrip())
            i -= 1
        params = sorted(set(re.findall(r"\$(\w+)", node.value.value)))
        out += [f"## `{name}`", "", " ".join(comment), "",
                f"**Parameters:** {', '.join(f'`${p}`' for p in params) or 'none'}  ",
                f"**Used by:** {USED_BY.get(name, '—')}", "", "```cypher", node.value.value.strip(), "```", ""]
    return out


if __name__ == "__main__":
    main()
