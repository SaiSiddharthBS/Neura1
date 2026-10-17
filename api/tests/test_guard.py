"""Never the same mistake twice: drafts and messages are checked against what the company already decided."""

from neura1 import chat, guard
from neura1.access import viewer
from neura1.ingest import extract


def test_proposing_a_rejected_part_brings_back_the_decision_and_its_proof(fresh_graph):
    extract.load_snapshots(fresh_graph)
    guard.forget()
    sai = viewer(fresh_graph, "P-SAI")
    for text in ("Let's switch PSM-28 to NB54361-L, it's pin-compatible and cheaper",
                 "We could try NB54361-L on the next build"):
        flags = guard.check(fresh_graph, text, sai)
        assert flags[0]["severity"] == "error" and flags[0]["record"] == "DEC-117"
        assert any("68C" in e["text"] for e in flags[0]["evidence"])  # the passage itself, word for word
    assert guard.check(fresh_graph, "NB54361-L was rejected, do not use it", sai) == []
    assert guard.check(fresh_graph, "Use Q-099 pricing", sai)[0]["title"] == "Q-099 has expired"


def test_leave_is_only_mentioned_to_people_who_may_see_it(fresh_graph):
    guard.forget()
    text = "Raghavendra will review the PSM-28 layout"
    assert guard.check(fresh_graph, text, viewer(fresh_graph, "P-SAI")) == []
    lead = guard.check(fresh_graph, text, viewer(fresh_graph, "P-HITHESH"))
    assert lead and "away" in lead[0]["title"]


def test_neura1_answers_a_message_that_repeats_a_rejected_idea(fresh_graph):
    extract.load_snapshots(fresh_graph)
    guard.forget()
    chat.ensure_channels(fresh_graph)
    m = chat.handle(fresh_graph, "chat/engineering", "Can we go for NB54361-L to save cost?", "Prakul", "P-PRAKUL")
    reply = chat.messages(fresh_graph, "chat/engineering")[-1]
    assert reply["author"] == chat.BOT and reply["kind"] == "guard" and reply["reply_to"] == m["id"]
    assert "DEC-117" in reply["text"] and "68C" in reply["text"]
    chat.handle(fresh_graph, "chat/engineering", "Bench is free after 3pm", "Prakul", "P-PRAKUL")
    assert chat.messages(fresh_graph, "chat/engineering")[-1]["author"] == "Prakul"  # silent when nothing is wrong
