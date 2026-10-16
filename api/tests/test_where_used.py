from pathlib import Path

import pytest

from neura1 import queries
from neura1.graph import rows
from neura1.ingest.structured import BomCycleError, check_bom_cycles, load_records


def where_used(graph, item_id):
    return {r["revision"]: r for r in rows(graph, queries.WHERE_USED, {"item_id": item_id})}


def test_quantity_rolls_up_across_nested_and_repeated_occurrences(graph):
    res = where_used(graph, "NB54360")
    # PDU-28 Rev C: 2x PSM-28 (1 each) + 1 direct on U12
    assert res["PDU-28-C"]["qty_per_unit"] == 3
    assert len(res["PDU-28-C"]["paths"]) == 2
    assert res["BCU-24-A"]["qty_per_unit"] == 1


def test_draft_and_obsolete_revisions_are_not_applicable(graph):
    res = where_used(graph, "NB54360")
    assert res["PDU-28-D"]["applicable"] is False
    assert res["PDU-28-D"]["paths"][0]["blocked_by"] == ["PDU-28-D"]
    assert res["PDU-28-B"]["applicable"] is False
    applicable = {rev for rev, r in res.items() if r["applicable"]}
    assert applicable == {"PDU-28-C", "BCU-24-A"}


def test_part_only_in_draft_has_no_applicable_use(graph):
    res = where_used(graph, "MX-3360")
    assert set(res) == {"PDU-28-D"}
    assert res["PDU-28-D"]["applicable"] is False


def test_reimport_is_idempotent(graph):
    count = "MATCH (n) WITH count(n) AS n MATCH ()-[r]->() RETURN n, count(r) AS r"
    before = rows(graph, count)
    load_records(graph)
    assert rows(graph, count) == before


def test_bom_cycle_is_rejected():
    bom = [
        {"parent_rev": "A-1", "child_rev": "B-1"},
        {"parent_rev": "B-1", "child_rev": "C-1"},
        {"parent_rev": "C-1", "child_rev": "A-1"},
    ]
    with pytest.raises(BomCycleError):
        check_bom_cycles(bom)
