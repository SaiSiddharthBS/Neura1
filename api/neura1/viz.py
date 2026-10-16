"""Turn an impact report into the evidence subgraph the UI draws. Every node and edge comes from a query result."""


def impact_subgraph(r: dict) -> dict:
    nodes: dict[str, dict] = {}
    edges: set[tuple[str, str, str]] = set()

    def node(id_, type_, label=None, **extra):
        nodes.setdefault(id_, {"id": id_, "type": type_, "label": label or id_, **extra})

    def edge(a, b, label):
        if a and b:
            edges.add((a, b, label))

    part = r["part"]
    node(part["id"], "part", part["id"], role="changed", name=part["name"])
    for u in r["where_used"]:
        for path in u["paths"]:
            ids = path["nodes"]
            for i, nid in enumerate(ids[:-1]):
                status = u["status"] if nid == u["revision"] else None
                node(nid, "revision", nid, status=status or ("blocked" if nid in path["blocked_by"] else "released"),
                     applicable=u["applicable"] if nid == u["revision"] else not path["blocked_by"])
                edge(nid, ids[i + 1], f"contains x{path['qty'] if i == len(ids) - 2 else ''}".rstrip("x "))
    for a in r["assemblies"]:
        if a["owner"]:
            node(a["owner"], "person")
            edge(a["owner"], a["revisions"][0], "owns")
    for b in r["builds"]:
        node(b["build"], "build", b["build"], at_risk=b["at_risk"], shortfall=b["shortfall"])
        edge(b["build"], b["revision"], "builds")
        if b["planner"]:
            node(b["planner"], "person")
            edge(b["planner"], b["build"], "plans")
        for o in b["orders"]:
            node(o["order"], "order", o["order"], due=o["due"], penalty=bool(o["penalty"]))
            node(o["customer_id"], "customer", o["customer"])
            edge(o["order"], b["build"], "fulfilled by")
            edge(o["customer_id"], o["order"], "placed")
    for f in r["field_units"]:
        node(f["shipment"], "shipment", f"{f['qty']} units in field", customer=f["customer"])
        edge(f["shipment"], f["revision"], "of")
    for d in r["dependents"]:
        node(d["id"], d["kind"], d["id"], name=d["name"])
        edge(d["id"], part["id"], "depends on")
        if d["owner"]:
            node(d["owner"], "person")
            edge(d["owner"], d["id"], "owns")
    for a in r["alternates"]:
        node(a["id"], "alternate", a["id"], status=a["status"])
        edge(a["id"], part["id"], "alternate of")
        for d in a["decisions"]:
            node(d["id"], "decision", d["id"], outcome=d["outcome"], authority=d["authority"])
            edge(d["id"], a["id"], d["outcome"])
            if d["decided_by"]:
                node(d["decided_by"], "person")
                edge(d["id"], d["decided_by"], "decided by")
    return {"nodes": list(nodes.values()),
            "edges": [{"source": a, "target": b, "label": l} for a, b, l in sorted(edges)]}
