"""Graph explorer: a record's neighbourhood and its history come straight from the graph."""

from neura1 import explore
from neura1.ingest import extract


def test_neighbourhood_links_a_part_to_its_decision_and_sources(fresh_graph):
    g = explore.neighborhood(fresh_graph, "NB54360")
    ids = {n["id"] for n in g["nodes"]}
    labels = {n["label"] for n in g["nodes"]}
    assert "NB54360" in ids and {"Item", "Source"} <= labels
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])


def test_timeline_is_newest_first_and_includes_leave(fresh_graph):
    events = explore.timeline(fresh_graph, "P-RAGHAVENDRA")
    dates = [e["at"] for e in events]
    assert dates == sorted(dates, reverse=True)
    assert any("2026-11-02" in e["at"] or "2026-11-02" in (e["detail"] or "") for e in events)


def test_a_decision_has_its_own_history_with_evidence(fresh_graph):
    extract.load_snapshots(fresh_graph)
    events = explore.timeline(fresh_graph, "DEC-117")
    assert events and events[-1]["at"].startswith("2025-03")
    assert any(e["kind"] == "decision" for e in events)
