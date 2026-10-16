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
}


def main() -> None:
    src = (REPO_ROOT / "api" / "neura1" / "queries.py").read_text()
    lines = src.splitlines()
    out = ["# Cypher queries Neura1 depends on", "",
           "Generated from [`api/neura1/queries.py`](../api/neura1/queries.py) by `uv run python -m neura1.docs`.",
           "All queries are parameterised and run read-only (`GRAPH.RO_QUERY`). Writes happen only in the loaders",
           "(`api/neura1/ingest/`) and in `api/neura1/actions.py`.", ""]
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
    (REPO_ROOT / "docs").mkdir(exist_ok=True)
    (REPO_ROOT / "docs" / "queries.md").write_text("\n".join(out))
    print("wrote docs/queries.md")


if __name__ == "__main__":
    main()
