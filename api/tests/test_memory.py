from neura1 import memory


def test_conversation_turns_are_linked_to_sources_and_records_and_recallable(fresh_graph):
    g = fresh_graph
    cid = memory.start(g, "P-SAI", "Who owns pmic_seq.c?")
    memory.record(g, cid, "Who owns pmic_seq.c?", {"answer": "Sai owns FW-PMIC-SEQ.", "tool_calls": [],
                                                    "sources": ["tickets/FW-233.json#description"]})
    memory.record(g, cid, "And who covers for Sai?", {"answer": "Vinay.", "tool_calls": [], "sources": []})
    assert [t["question"] for t in memory.history(g, cid)] == ["Who owns pmic_seq.c?", "And who covers for Sai?"]
    t = memory.transcript(g, cid)
    assert t[0]["sources"] == ["tickets/FW-233.json#description"]
    assert memory.conversations(g, "P-SAI")[0]["turns"] == 2
    recalled = memory.recall(g, "FW-PMIC-SEQ")      # found through the ABOUT link, not text
    assert recalled and recalled[0]["asked_by"] == "Sai"
