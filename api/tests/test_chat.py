"""Neura1 Chat: messages become linked knowledge; commands answer from the graph without a model."""

from neura1 import brain, chat


def test_message_becomes_linked_knowledge_and_feeds_who_knows(fresh_graph):
    chat.ensure_channels(fresh_graph)
    before = {p["name"]: p["score"] for p in brain.who_knows(fresh_graph, "CT-1051")["people"]}
    m = chat.handle(fresh_graph, "chat/engineering", "Pruthvi here: the CT-1051 bus-off test passes on the rig now.",
                    "Pruthvi", "P-PRUTHVI")
    assert "CT-1051" in m["about"]
    after = {p["name"]: p["score"] for p in brain.who_knows(fresh_graph, "CT-1051")["people"]}
    assert after.get("Pruthvi", 0) > before.get("Pruthvi", 0)
    msgs = chat.messages(fresh_graph, "chat/engineering")
    assert msgs[-1]["author"] == "Pruthvi"


def test_commands_answer_from_the_graph(fresh_graph):
    chat.ensure_channels(fresh_graph)
    chat.handle(fresh_graph, "chat/supply", "/impact NB54360 320 22", "Ambika", "P-AMBIKA")
    reply = chat.messages(fresh_graph, "chat/supply")[-1]
    assert reply["author"] == chat.BOT and "PDU-28-C (3/unit)" in reply["text"] and "₹37,400" in reply["text"]
    assert "NB54361-L" not in reply["text"] or "Do not switch" in reply["text"]
    assert "Raghavendra is away 2026-11-02" in chat.command(fresh_graph, "/away Raghavendra")["text"]
    assert "Sai" in chat.command(fresh_graph, "/who CAN bus")["text"]
    assert "NB54360" in chat.command(fresh_graph, "/risk")["text"]


def test_direct_messages_have_two_members(fresh_graph):
    cid = chat.dm_channel(fresh_graph, "P-SAI", "P-VINAY")
    assert cid == chat.dm_channel(fresh_graph, "P-VINAY", "P-SAI")
    names = [c["name"] for c in chat.channels(fresh_graph, "P-SAI")]
    assert "Sai & Vinay" in names and "Sai & Vinay" not in [c["name"] for c in chat.channels(fresh_graph, "P-UDAY")]


def test_replies_only_show_what_every_reader_may_see(fresh_graph):
    chat.ensure_channels(fresh_graph)
    public = chat.Audience(fresh_graph, "chat/engineering")
    assert "2026-11-02" not in chat.command(fresh_graph, "/away Raghavendra", public)["text"]
    assert "₹" not in chat.command(fresh_graph, "/impact NB54360 320 22", public)["text"]
    assert "₹37,400" in chat.command(fresh_graph, "/impact NB54360 320 22", chat.Audience(fresh_graph, "chat/supply"))["text"]
    dm = chat.dm_channel(fresh_graph, "P-VISHWAS", "P-HITHESH")          # manager chain of Raghavendra
    assert "2026-11-02" in chat.command(fresh_graph, "/away Raghavendra", chat.Audience(fresh_graph, dm))["text"]
    dm2 = chat.dm_channel(fresh_graph, "P-VISHWAS", "P-PRUTHVI")          # Pruthvi may not see it
    assert "2026-11-02" not in chat.command(fresh_graph, "/away Raghavendra", chat.Audience(fresh_graph, dm2))["text"]
    assert chat.redact_text("It costs ₹37,400 now.", public) == "It costs [amount hidden in this channel] now."
