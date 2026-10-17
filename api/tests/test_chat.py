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
    chat.handle(fresh_graph, "chat/leadership", "/impact NB54360 320 22", "Hithesh", "P-HITHESH")
    reply = chat.messages(fresh_graph, "chat/leadership")[-1]
    assert reply["author"] == chat.BOT and "PDU-28-C (3/unit)" in reply["text"] and "₹37,400" in reply["text"]
    assert reply["reply"]["author"] == "Hithesh"  # the answer is threaded to the question
    assert "NB54361-L" not in reply["text"] or "Do not switch" in reply["text"]
    assert "Raghavendra is away 2026-11-02" in chat.command(fresh_graph, "/away Raghavendra")["text"]
    assert "Sai" in chat.command(fresh_graph, "/who CAN bus")["text"]
    assert "NB54360" in chat.command(fresh_graph, "/risk")["text"]


def test_direct_messages_have_two_members(fresh_graph):
    cid = chat.dm_channel(fresh_graph, "P-SAI", "P-VINAY")
    assert cid == chat.dm_channel(fresh_graph, "P-VINAY", "P-SAI")
    mine = [c for c in chat.channels(fresh_graph, "P-SAI") if c["kind"] == "dm"]
    assert [c["name"] for c in mine] == ["Vinay"]  # a direct message is named after the other person
    assert cid not in [c["id"] for c in chat.channels(fresh_graph, "P-UDAY")]


def test_replies_only_show_what_every_reader_may_see(fresh_graph):
    chat.ensure_channels(fresh_graph)
    public = chat.Audience(fresh_graph, "chat/engineering")
    assert "2026-11-02" not in chat.command(fresh_graph, "/away Raghavendra", public)["text"]
    assert "₹" not in chat.command(fresh_graph, "/impact NB54360 320 22", public)["text"]
    assert "₹" not in chat.command(fresh_graph, "/impact NB54360 320 22", chat.Audience(fresh_graph, "chat/supply"))["text"]
    assert "₹37,400" in chat.command(fresh_graph, "/impact NB54360 320 22", chat.Audience(fresh_graph, "chat/leadership"))["text"]
    dm = chat.dm_channel(fresh_graph, "P-VISHWAS", "P-HITHESH")          # Raghavendra's backup, and the CTO
    assert "2026-11-02" in chat.command(fresh_graph, "/away Raghavendra", chat.Audience(fresh_graph, dm))["text"]
    dm2 = chat.dm_channel(fresh_graph, "P-VISHWAS", "P-PRUTHVI")          # Pruthvi may not see it
    assert "2026-11-02" not in chat.command(fresh_graph, "/away Raghavendra", chat.Audience(fresh_graph, dm2))["text"]
    assert chat.redact_text("It costs ₹37,400 now.", public) == "It costs [amount hidden in this channel] now."


def _ids(graph, viewer):
    return {c["id"]: c for c in chat.channels(graph, viewer)}


def test_groups_are_private_to_their_members(fresh_graph):
    from neura1.access import viewer
    import pytest
    gid = chat.create_group(fresh_graph, "P-SAI", "PMIC bring-up", ["P-VINAY", "P-MANOJ"])
    assert gid in _ids(fresh_graph, "P-VINAY") and gid not in _ids(fresh_graph, "P-UDAY")
    with pytest.raises(chat.ChatError):
        chat.may_read(chat.channel(fresh_graph, gid), viewer(fresh_graph, "P-UDAY"))
    with pytest.raises(chat.ChatError):
        chat.create_group(fresh_graph, "P-SAI", "Two of us", ["P-VINAY"])  # that is a direct message
    m = chat.handle(fresh_graph, gid, "Vinay, can you check CT-1051 on the rig?", "Sai", "P-SAI")
    # Group messages are private: never company knowledge, never in search.
    assert fresh_graph.query("MATCH (c:Chunk {id:$id}) RETURN c", {"id": m["id"]}).result_set == []
    chat.add_members(fresh_graph, gid, "P-VINAY", ["P-UDAY"])
    assert gid in _ids(fresh_graph, "P-UDAY")
    with pytest.raises(chat.ChatError):
        chat.remove_member(fresh_graph, gid, "P-VINAY", "P-MANOJ")  # only the creator removes others
    chat.remove_member(fresh_graph, gid, "P-MANOJ", "P-MANOJ")       # anyone may leave
    assert gid not in _ids(fresh_graph, "P-MANOJ")
    texts = [x["text"] for x in chat.messages(fresh_graph, gid) if x["kind"] == "system"]
    assert texts[0].startswith("Sai created the group") and "Manoj left the group" in texts


def test_unread_counts_mentions_and_read_receipts(fresh_graph):
    dm = chat.dm_channel(fresh_graph, "P-SAI", "P-VINAY")
    chat.mark_read(fresh_graph, dm, "P-VINAY")
    chat.handle(fresh_graph, dm, "Morning! @Vinay please review pmic_seq.c today", "Sai", "P-SAI")
    chat.handle(fresh_graph, dm, "and the bootloader notes", "Sai", "P-SAI")
    vinay = _ids(fresh_graph, "P-VINAY")[dm]
    assert vinay["unread"] == 2 and vinay["mentions"] == 1 and vinay["preview"]["text"] == "and the bootloader notes"
    assert _ids(fresh_graph, "P-SAI")[dm]["unread"] == 0  # your own messages are never unread
    assert chat.unread(fresh_graph, "P-VINAY", "Vinay")["total"] >= 2
    chat.mark_read(fresh_graph, dm, "P-VINAY")
    assert _ids(fresh_graph, "P-VINAY")[dm]["unread"] == 0
    last = chat.messages(fresh_graph, dm)[-1]
    assert chat.read_state(fresh_graph, dm)["P-VINAY"] >= last["ts"]  # Sai sees "Seen"


def test_replies_edits_deletes_and_reactions(fresh_graph):
    import pytest
    chat.ensure_channels(fresh_graph)
    q = chat.handle(fresh_graph, "chat/engineering", "Is CT-1051 still on allocation?", "Pruthvi", "P-PRUTHVI")
    a = chat.handle(fresh_graph, "chat/engineering", "Yes, until December.", "Ambika", "P-AMBIKA", reply_to=q["id"])
    since = chat.recent_cursor()
    with pytest.raises(chat.ChatError):
        chat.edit_message(fresh_graph, a["id"], "P-PRUTHVI", "No.")  # not your message
    chat.edit_message(fresh_graph, a["id"], "P-AMBIKA", "Yes, until December per SUP-1042.")
    chat.react(fresh_graph, q["id"], "P-SAI", "👍")
    chat.react(fresh_graph, q["id"], "P-VINAY", "👍")
    chat.react(fresh_graph, q["id"], "P-VINAY", "👍")  # a second tap takes it back
    changed = {m["id"]: m for m in chat.messages(fresh_graph, "chat/engineering", since)}
    assert changed[q["id"]]["reactions"] == {"👍": ["P-SAI"]}
    assert changed[a["id"]]["edited_at"] and "SUP-1042" in changed[a["id"]]["text"]
    assert changed[a["id"]]["reply"]["author"] == "Pruthvi"
    chat.delete_message(fresh_graph, q["id"], "P-PRUTHVI")
    msgs = {m["id"]: m for m in chat.messages(fresh_graph, "chat/engineering")}
    assert msgs[q["id"]]["deleted"] and msgs[q["id"]]["text"] == "" and msgs[a["id"]]["reply"]["deleted"]
    # A deleted message leaves company knowledge: no text, no links.
    left = fresh_graph.query("MATCH (c:Chunk {id:$id})-[:MENTIONS]->() RETURN count(*)", {"id": q["id"]}).result_set
    assert left[0][0] == 0


def test_search_typing_and_new_channels(fresh_graph):
    from neura1.access import viewer
    import pytest
    dm = chat.dm_channel(fresh_graph, "P-SAI", "P-VINAY")
    chat.handle(fresh_graph, dm, "the brown-out log is on the share", "Sai", "P-SAI")
    assert [m["channel"] for m in chat.search(fresh_graph, viewer(fresh_graph, "P-VINAY"), "brown-out")] == [dm]
    assert chat.search(fresh_graph, viewer(fresh_graph, "P-UDAY"), "brown-out") == []
    chat.typing(dm, "P-SAI", "Sai")
    assert chat.who_is_typing(dm, "P-VINAY") == ["Sai"] and chat.who_is_typing(dm, "P-SAI") == []
    cid = chat.create_channel(fresh_graph, "P-SAI", "PDU-48 bring up", "Bench work for the PDU-48")
    assert cid == "chat/pdu-48-bring-up" and cid in _ids(fresh_graph, "P-UDAY")
    with pytest.raises(chat.ChatError):
        chat.create_channel(fresh_graph, "P-VINAY", "pdu-48 bring-up", None)
    with pytest.raises(chat.ChatError):
        chat.update_conversation(fresh_graph, "chat/general", "P-SAI", name="random")
