"""End-to-end through the HTTP API on the test graph: trace → approve → re-approve → update → diff."""

import pytest
from fastapi.testclient import TestClient

from neura1 import main
from neura1.config import settings

NOTICE = "inbox/notice_NB54360_2026-10-14.md"
BODY = {"item": "NB54360", "new_unit_price": 320, "lead_weeks": 22, "as_of": "2026-10-16"}  # what-if: its own investigation


@pytest.fixture
def client(fresh_graph):
    main.app.dependency_overrides[main.graph] = lambda: fresh_graph
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_full_flow(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_passcode", "test-pass")  # this flow also checks that a set passcode is enforced
    pw = {"x-demo-passcode": "test-pass"}
    r = client.post("/api/impact", json=BODY).json()
    assert r["cost"]["total_delta"] in (37400, "37400")

    approve = {"item_id": "NB54360", "approved_by": "Hithesh",
               "new_unit_price": "320", "lead_weeks": 22}
    assert client.post("/api/actions/approve?as_of=2026-10-16", json=approve).status_code == 403
    first = client.post("/api/actions/approve?as_of=2026-10-16", json=approve, headers=pw).json()
    again = client.post("/api/actions/approve?as_of=2026-10-16", json=approve, headers=pw).json()
    assert again["created"] == [] and len(again["already_existed"]) == len(first["created"]) + len(first["already_existed"])

    reopened = client.post("/api/impact", json=BODY).json()
    assert reopened["investigation"]["approved_by"] == "Hithesh"

    assert client.post("/api/updates/apply", headers=pw).status_code == 200
    after = client.post("/api/impact", json=BODY).json()
    assert any("Q-140" in c for c in after["changes_since_approval"]), after["changes_since_approval"]


def test_graph_unavailable_is_503_not_a_fallback(client):
    from neura1.graph import GraphUnavailable

    def down():
        raise GraphUnavailable("down")

    main.app.dependency_overrides[main.graph] = down
    res = client.post("/api/impact", json=BODY)
    assert res.status_code == 503 and res.json()["error"] == "graph_unavailable"


def test_changes_are_open_unless_a_passcode_is_set(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_passcode", None)
    assert client.get("/api/health").json()["passcode_required"] is False
    sai = {"x-neura1-as": "P-SAI"}
    assert client.post("/api/chat/messages", json={"channel": "chat/general", "text": "hello"}, headers=sai).status_code == 200
    monkeypatch.setattr(settings, "demo_passcode", "s3cret")
    r = client.post("/api/chat/messages", json={"channel": "chat/general", "text": "hello"}, headers=sai)
    assert r.status_code == 403 and r.json()["detail"] == "Writes need the demo passcode"
    r = client.post("/api/chat/messages", json={"channel": "chat/general", "text": "hello again"},
                    headers=sai | {"x-demo-passcode": "s3cret"})
    assert r.status_code == 200
