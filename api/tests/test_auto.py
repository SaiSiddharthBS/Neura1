"""The DGX worker reads new information on its own: chat decisions and task skill tags, verified like everything else.
Model outputs below are hand-written test inputs, not model results."""

from neura1 import auto, chat
from neura1.config import settings
from neura1.graph import rows
from neura1.ingest import extract


def test_live_snapshots_never_land_in_the_fixture():
    assert extract.snapshot_path("chats/slack_hw-power_2025-03.json", "decisions").is_relative_to(settings.fixture_dir)
    assert extract.snapshot_path("chat/engineering", "decisions").is_relative_to(settings.data_dir)
    assert extract.snapshot_path("documents/DOC-1.md", "actions").is_relative_to(settings.data_dir)


def test_a_chat_decision_is_read_verified_and_announced(fresh_graph, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(auto, "QUIET_SECONDS", 0)
    chat.ensure_channels(fresh_graph)
    msg = "Decision: we reject NB54361-L for PSM-28 Rev 2 again, the 68C shutdown is not acceptable."
    chat.post(fresh_graph, "chat/engineering", msg, "Vishwas", "P-VISHWAS")
    chat.post(fresh_graph, "chat/engineering", "Noted.", chat.BOT, None)
    stale = [s["id"] for s in auto.stale_sources(fresh_graph)]
    assert stale == ["chat/engineering"]  # fixture documents are never re-read

    seen = {}

    def fake_model(graph, source_id, kind, passages=None):
        seen["authors"] = {p["author"] for p in passages}
        chunk = passages[0]["id"]
        snap = {"source_id": source_id, "kind": kind, "model": "test-input", "extracted_at": "2026-10-17T00:00:00+00:00",
                "output": {"decisions": [{
                    "outcome": "rejected", "subject": "NB54361-L", "instead_of": "NB54360", "applies_to": ["PSM-28 Rev 2"],
                    "summary": "NB54361-L rejected again for PSM-28 Rev 2", "reason": "68C shutdown",
                    "decided_by": "Vishwas", "decided_at": "2026-10-17", "ref": None,
                    "evidence": [{"chunk_id": chunk, "quote": "we reject NB54361-L for PSM-28 Rev 2 again"}]}]}}
        return snap
    monkeypatch.setattr(extract, "run_model", fake_model)
    out = auto.read_source(fresh_graph, {"id": "chat/engineering", "kind": "chat", "title": "Neura1 Chat #engineering",
                                         "version": stale and auto.stale_sources(fresh_graph)[0]["version"]})
    assert seen["authors"] == {"Vishwas"}  # Neura1's own replies are not mined
    assert len(out["decisions"]) == 1
    assert auto.stale_sources(fresh_graph) == []
    notes = rows(fresh_graph, "MATCH (c:Chunk {kind:'notice'})-[:PART_OF]->(:Source {id:'chat/engineering'}) RETURN c.text AS t")
    assert any("checked word for word" in n["t"] for n in notes)


def test_new_tasks_are_tagged_with_known_skills_only(fresh_graph, monkeypatch):
    from neura1 import actions
    t = actions.create_task(fresh_graph, "Review pmic_seq.c soft-start for MX-3360", "Sai", "FW-PMIC-SEQ", "test", "Hithesh")
    tid = t["id"]

    def fake_chat_json(system, user, schema, name):
        return {"tags": [{"id": tid, "skills": ["Embedded C", "Power sequencing", "Telepathy"]}]}
    monkeypatch.setattr("neura1.llm.chat_json", fake_chat_json)
    assert auto.tag_new_tasks(fresh_graph) >= 1
    skills = {r["s"] for r in rows(fresh_graph, "MATCH (:Action {id:$id})-[:NEEDS_SKILL]->(s:Skill) RETURN s.name AS s", {"id": tid})}
    assert skills == {"Embedded C", "Power sequencing"}
    assert auto.tag_new_tasks(fresh_graph) == 0 or tid not in str(rows(fresh_graph, "MATCH (a:Action) WHERE a.skills_tagged_at IS NULL RETURN a.id AS id"))
