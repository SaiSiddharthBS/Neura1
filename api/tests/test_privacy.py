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
