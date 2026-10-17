"""Neura1 Docs: templates from the graph, rule-based fact checks, saving as knowledge, and who may open what."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from neura1 import documents, main
from neura1.access import viewer
from neura1.config import settings
from neura1.ingest import extract


@pytest.fixture
def client(fresh_graph, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    extract.load_snapshots(fresh_graph)
    main.app.dependency_overrides[main.graph] = lambda: fresh_graph
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


CTO = {"x-neura1-as": "P-HITHESH", "x-demo-passcode": settings.demo_passcode or ""}
ENGINEER = {"x-neura1-as": "P-ANIRUDH"}


def _docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


def test_change_notice_is_composed_from_the_graph(client):
    r = client.post("/api/docs", json={"template": "change_notice", "record": "NB54360"}, headers=CTO).json()
    md = r["markdown"]
    assert "BO-0412" in md and "SO-881 (Nilgiri Aero Systems)" in md
    assert "DEC-117: rejected on 2025-03-12 by Vishwas" in md and "₹37,400" in md
    assert "Approved by (Chief Technology Officer)" in md and "Hithesh" in md


def test_fact_check_flags_contradictions_with_their_reasons(fresh_graph):
    extract.load_snapshots(fresh_graph)
    blocks = [{"id": "a", "text": "We will switch NB54360 to NB54361-L to save cost, per Q-099."},
              {"id": "b", "text": "MX-3360 is approved. Raghavendra will review PSM-28 Rev 1 for SO-889."},
              {"id": "c", "text": "We will not use NB54361-L (rejected in DEC-117)."}]
    flags = documents.check(fresh_graph, blocks, viewer(fresh_graph, "P-HITHESH"))
    titles = {(f["block_id"], f["title"]) for f in flags}
    assert ("a", "NB54361-L was rejected (DEC-117)") in titles
    assert ("a", "Q-099 has expired") in titles
    assert ("b", "MX-3360 is not approved") in titles
    assert ("b", "PSM-28-1 is obsolete") in titles
    assert ("b", "SO-889 is not in the records") in titles
    assert any(t[1].startswith("Raghavendra is away") for t in titles)
    assert not any(f["block_id"] == "c" for f in flags)
    assert all(f["quote"] in next(b["text"] for b in blocks if b["id"] == f["block_id"]) for f in flags)
    # Leave is only mentioned to people who may see it.
    engineer = documents.check(fresh_graph, blocks, viewer(fresh_graph, "P-ANIRUDH"))
    assert not any("away" in f["title"] for f in engineer)


def test_saved_document_becomes_linked_knowledge_and_money_stays_closed(client):
    doc = client.post("/api/docs", json={"template": "blank", "title": "Note"}, headers=CTO).json()["id"]
    r = client.put(f"/api/docs/{doc}", files={"file": ("n.docx", _docx())},
                   data={"title": "NB54360 note", "blocks": json.dumps(["Keep NB54360; Q-101 is ₹250."])}, headers=CTO).json()
    assert r["shared"] and {"NB54360", "Q-101"} <= set(r["linked"]) and r["audience"] == "money"
    assert client.get(f"/api/docs/{doc}/file", headers=ENGINEER).status_code == 403
    assert client.get(f"/api/docs/{doc}/file", headers=CTO).status_code == 200
    assert doc not in [d["id"] for d in client.get("/api/docs", headers=ENGINEER).json()]


def test_handover_notes_follow_the_leave_rule_and_stay_out_of_search(client, fresh_graph):
    assert client.post("/api/docs", json={"template": "handover", "record": "P-RAGHAVENDRA"},
                       headers={**CTO, "x-neura1-as": "P-ANIRUDH"}).status_code == 403
    doc = client.post("/api/docs", json={"template": "handover", "record": "P-RAGHAVENDRA"}, headers=CTO).json()["id"]
    r = client.put(f"/api/docs/{doc}", files={"file": ("h.docx", _docx())},
                   data={"title": "Handover", "blocks": json.dumps(["Handover marker 7Q: away in November."])}, headers=CTO).json()
    assert r["shared"] is False
    from neura1.graph import rows
    assert rows(fresh_graph, "MATCH (c:Chunk) WHERE c.text CONTAINS 'Handover marker 7Q' RETURN count(c) AS n")[0]["n"] == 0
    assert doc not in [d["id"] for d in client.get("/api/docs", headers=ENGINEER).json()]


def test_model_inventions_are_reported():
    assert documents.invented("Order SO-881 for 80 units", [], "Order SO-881 for 90 units, see SO-999") == ["90", "SO-999"]
