"""Re-importing changed documents keeps links, flags edited evidence, and retracts removed passages."""

import json

from neura1 import brain
from neura1.ingest.extract import load_decisions
from neura1.ingest.unstructured import load_sources

THREAD = {"channel": "#hw-test", "messages": [
    {"id": "m1", "ts": "2026-01-01T10:00:00+05:30", "user": "Vishwas",
     "text": "Decision: we reject NB54361-L instead of NB54360 on PSM-28 Rev 2. Logging as DEC-900."},
    {"id": "m2", "ts": "2026-01-01T11:00:00+05:30", "user": "Raghavendra", "text": "Noted."}]}


def test_edited_and_removed_evidence_is_flagged_not_lost(fresh_graph, tmp_path):
    g = fresh_graph
    chats = tmp_path / "chats"
    chats.mkdir()
    path = chats / "thread.json"
    path.write_text(json.dumps(THREAD))
    load_sources(g, root=tmp_path, files=[path])
    load_decisions(g, {"source_id": "chats/thread.json", "model": "test-input", "extracted_at": "2026-01-02",
                       "output": {"decisions": [{
                           "outcome": "rejected", "subject": "NB54361-L", "instead_of": "NB54360",
                           "summary": "rejected", "ref": "DEC-900",
                           "evidence": [{"chunk_id": "chats/thread.json#m1",
                                         "quote": "we reject NB54361-L instead of NB54360"}]}]}})
    assert brain.changes(g)["attention"] == [] or all(a["record"] != "DEC-900" for a in brain.changes(g)["attention"])

    # Someone edits the decision message, and the other message is deleted.
    edited = {**THREAD, "messages": [{**THREAD["messages"][0], "text": THREAD["messages"][0]["text"] + " (edited)"}]}
    path.write_text(json.dumps(edited))
    load_sources(g, root=tmp_path, files=[path])

    linked = g.ro_query("MATCH (:Decision {id:'DEC-900'})-[:EVIDENCED_BY]->(c) RETURN c.id").result_set
    assert linked == [["chats/thread.json#m1"]]            # the link survived the re-import
    flags = {a["record"]: a["reason"] for a in brain.changes(g)["attention"]}
    assert "edited" in flags["DEC-900"]                    # and the edit is flagged
    gone = g.ro_query("MATCH (c:Chunk {id:'chats/thread.json#m2'}) RETURN c").result_set
    assert gone == []                                      # uncited passage that vanished is removed


def test_who_knows_ranks_owner_and_decision_maker(graph):
    r = brain.who_knows(graph, "pmic_seq.c")              # resolved through an alias
    assert r["subject"]["id"] == "FW-PMIC-SEQ"
    assert r["people"][0]["name"] == "Sai"
