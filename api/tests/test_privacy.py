"""Direct messages stay private, money channels stay closed, and amounts never leak through free text."""

from fastapi.testclient import TestClient

from neura1 import chat, main
from neura1.access import redact_money_text
from neura1.graph import rows


def test_direct_messages_never_become_shared_knowledge(fresh_graph):
    cid = chat.dm_channel(fresh_graph, "P-SAI", "P-VINAY")
    chat.post(fresh_graph, cid, "Between us: CT-1051 firmware is late again.", "Sai", "P-SAI")
    assert chat.messages(fresh_graph, cid)[-1]["text"].startswith("Between us")
    # Every knowledge query (search, who knows, timelines, the agent) reads Chunk passages; a DM is never one.
    assert rows(fresh_graph, "MATCH (c:Chunk) WHERE c.text CONTAINS 'Between us' RETURN count(c) AS n")[0]["n"] == 0
    from neura1 import explore
    assert not any("Between us" in (e["detail"] or "") for e in explore.timeline(fresh_graph, "CT-1051"))
    assert not any(n["label"] == "Message" for n in explore.neighborhood(fresh_graph, "P-SAI")["nodes"])


def test_amounts_in_text_are_hidden():
    assert redact_money_text({"t": ["Penalty ₹4,20,000 and INR 182.50"]}) == {"t": ["Penalty [amount hidden] and [amount hidden]"]}


def test_money_channels_are_closed_to_engineers(fresh_graph):
    main.app.dependency_overrides[main.graph] = lambda: fresh_graph
    c = TestClient(main.app)
    chans = [x["id"] for x in c.get("/api/chat/channels", headers={"x-neura1-as": "P-SAI"}).json()]
    assert "chat/leadership" not in chans and "chat/general" in chans
    assert c.get("/api/chat/messages?channel=chat/leadership", headers={"x-neura1-as": "P-SAI"}).status_code == 403
    assert c.get("/api/chat/messages?channel=chat/leadership", headers={"x-neura1-as": "P-JAYARAM"}).status_code == 200
    main.app.dependency_overrides.clear()


def test_leave_notices_stay_with_people_allowed_to_see_the_leave(fresh_graph):
    main.app.dependency_overrides[main.graph] = lambda: fresh_graph
    import neura1.main as m
    orig = m.get_graph
    m.get_graph = lambda name=None: fresh_graph  # the safety net reads the same graph as the endpoints
    try:
        c = TestClient(main.app)
        engineer, lead = {"x-neura1-as": "P-ANIRUDH"}, {"x-neura1-as": "P-HITHESH"}
        q = "/api/search?q=Raghavendra%20planned%20leave"
        hits = lambda h: [x["chunk"] for x in c.get(q, headers=h).json()["hits"]]
        assert not any(x.startswith("inbox/leave_") for x in hits(engineer))
        assert any(x.startswith("inbox/leave_") for x in hits(lead))
        leave_chunk = next(x for x in hits(lead) if x.startswith("inbox/leave_"))
        from urllib.parse import quote
        assert c.get(f"/api/evidence?chunk_id={quote(leave_chunk, safe='')}", headers=engineer).status_code == 403
        assert c.get(f"/api/evidence?chunk_id={quote(leave_chunk, safe='')}", headers=lead).status_code == 200
        assert not any(s["kind"] == "leave" for s in c.get("/api/signals", headers=engineer).json())
    finally:
        m.get_graph = orig
        main.app.dependency_overrides.clear()


def test_ai_requests_are_rate_limited_per_visitor(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from starlette.requests import Request
    monkeypatch.setattr(main.settings, "ai_per_minute", 2)
    main._ai_calls.clear()
    req = lambda ip: Request({"type": "http", "headers": [(b"cf-connecting-ip", ip.encode())], "client": ("1.1.1.1", 1)})
    main.ai_rate_limit(req("10.0.0.1"))
    main.ai_rate_limit(req("10.0.0.1"))
    with pytest.raises(HTTPException) as e:
        main.ai_rate_limit(req("10.0.0.1"))
    assert e.value.status_code == 429
    main.ai_rate_limit(req("10.0.0.2"))  # another visitor is not affected
    main._ai_calls.clear()
