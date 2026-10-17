"""Raise the purchase order, stock-out forecasts, knowledge health, personal briefs and meeting recordings."""

import time
from datetime import date

import pytest

from neura1 import brief, chat, inventory, knowledge_health, meetings, purchasing
from neura1.access import viewer
from neura1.ingest import extract

TODAY = date(2026, 10, 17)


def test_neura1_drafts_the_order_and_a_person_raises_it(fresh_graph):
    extract.load_snapshots(fresh_graph)
    d = purchasing.suggest(fresh_graph, "NB54360", TODAY, "Hithesh")
    assert d["qty"] == 600 and d["unit_price"] == 250 and d["quote_id"] == "Q-101"   # 570 needed, MOQ 100
    assert d["saving_vs_notice"] == 600 * 70                                        # ordered before the ₹320 notice
    assert d["misses"] == ["BO-0412", "BO-0415", "BO-0421"] and d["expected_on"] == "2027-03-20"
    assert any("NB54361-L" in w for w in d["warnings"]) and any("Last-time-buy" in w for w in d["warnings"])
    assert purchasing.suggest(fresh_graph, "KP8081", TODAY)["misses"] == []        # free stock covers its builds
    assert purchasing.suggest(fresh_graph, "CT-1051", TODAY)["status"] == "needs_quote"

    po = purchasing.create(fresh_graph, "NB54360", None, "Hithesh", TODAY)
    assert po["id"] == "PO-2026-0132" and po["qty"] == 600
    assert inventory.item(fresh_graph, "NB54360", TODAY)["stock"]["on_order"] == 600
    assert not purchasing.suggest(fresh_graph, "NB54360", TODAY)["needed"]          # nothing more to order

    r = purchasing.receive(fresh_graph, po["id"], 300, 10, "L-TEST", "Hithesh", TODAY)
    assert r["accepted"] == 290 and r["status"] == "partially_received"
    nb = inventory.item(fresh_graph, "NB54360", TODAY)
    assert nb["stock"]["on_hand"] == 180 + 290 and nb["ledger"][-1]["balance"] == nb["stock"]["on_hand"]
    with pytest.raises(purchasing.PurchasingError):
        purchasing.receive(fresh_graph, po["id"], 301, 0, None, "Hithesh", TODAY)   # only 300 still to come


def test_stock_outs_are_predicted_with_an_order_by_date(graph):
    rows = {r["id"]: r for r in inventory.items(graph, TODAY)}
    assert rows["KP8081"]["forecast"]["order_by"] == "2026-11-11"
    nb = rows["NB54360"]["forecast"]
    assert nb["runs_short"]["date"] == "2026-11-03" and nb["late"]
    assert rows["VX7-MCU"]["outlook"] is None                                        # covered by the order on its way


def test_knowledge_health_finds_stale_facts_in_living_documents(fresh_graph):
    extract.load_snapshots(fresh_graph)
    lead = knowledge_health.sweep(fresh_graph, viewer(fresh_graph, "P-HITHESH"), TODAY)
    guide = next(d for d in lead["documents"] if d["id"].endswith("buying_guide_power_stage.md"))
    kinds = {f["kind"] for f in guide["findings"]}
    assert guide["owner"] == "Ambika" and {"contradicts", "lead_time", "superseded", "away"} <= kinds
    assert any(f["quote"] == "6 weeks" and "22 weeks" in f["message"] for f in guide["findings"])
    assert not any("weekly" in d["id"] or "TR-112" in d["id"] for d in lead["documents"])   # dated records are left alone
    employee = knowledge_health.sweep(fresh_graph, viewer(fresh_graph, "P-PRAKUL"), TODAY)
    g2 = next(d for d in employee["documents"] if d["id"] == guide["id"])
    assert "away" not in {f["kind"] for f in g2["findings"]}                         # leave only for those allowed
    task = knowledge_health.request_review(fresh_graph, guide["id"], viewer(fresh_graph, "P-HITHESH"))
    assert task["owner"] == "Ambika"


def test_each_person_gets_their_own_brief_in_private(fresh_graph):
    extract.load_snapshots(fresh_graph)
    ambika = brief.personal(fresh_graph, "P-AMBIKA", TODAY)["text"]
    assert "NB54360 runs short" in ambika and "Buying guide" in ambika and "5 out-of-date facts" in ambika
    prakul = brief.personal(fresh_graph, "P-PRAKUL", TODAY)["text"]
    assert "₹" not in prakul and "Buying guide" not in prakul
    sent = brief.post_personal(fresh_graph, "P-AMBIKA", TODAY)
    assert sent and brief.post_personal(fresh_graph, "P-AMBIKA", TODAY) is None     # once a day
    ch = chat.channel(fresh_graph, sent["channel"])
    assert ch["kind"] == "bot" and ch["members"] == ["P-AMBIKA"]
    with pytest.raises(chat.ChatError):
        chat.may_read(ch, viewer(fresh_graph, "P-SAI"))
    people = fresh_graph.query("MATCH (p:Person) RETURN count(p)").result_set[0][0]
    assert brief.post_everyone(fresh_graph, TODAY) == people - 1                     # Ambika already has hers
    assert brief.post_everyone(fresh_graph, TODAY) == 0                              # and nobody gets two


def test_identifiers_and_names_are_put_back_in_their_graph_form():
    assert meetings.canonical("using the 60CT-1051 and BO 0415", ["CT-1051", "BO-0415"]) == "using the 60 CT-1051 and BO-0415"
    assert meetings.fix_names("Hitesh here. Ask Raghavendr.", ["Hithesh", "Raghavendra"]) == "Hithesh here. Ask Raghavendra."
    assert meetings.fix_orgs("from Dakton components", ["Deccan Components (distributor)"]) == "from Deccan Components"
    words = [{"start": i, "end": i + 0.5, "word": w} for i, w in enumerate(" Sai here, ready. Ambika here, done.".split(" ")[1:])]
    segs = meetings.words_to_segments([dict(w, word=" " + w["word"]) for w in words])
    assert [s["text"].split()[0] for s in segs] == ["Sai", "Ambika"]


def test_a_recording_becomes_verified_decisions_and_actions(fresh_graph, monkeypatch, tmp_path):
    from neura1 import llm
    from neura1.config import settings
    extract.load_snapshots(fresh_graph)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    segs = [{"start": 0.0, "end": 6.0, "text": "Hithesh here, decision, we build BO-0415 on the 10th using the CT-1051 units in stock."},
            {"start": 6.5, "end": 11.0, "text": "Ambika here, I will request quotes for CT-1051 by Monday."}]
    monkeypatch.setattr(meetings, "transcribe", lambda path, prompt: (segs, 11.0, "test transcript"))
    monkeypatch.setattr(llm, "status", lambda: {"on_fallback": False})

    def fake_model(graph, source_id, kind, passages=None):  # hand-written test inputs, not model output
        p0, p1 = passages[0]["id"], passages[1]["id"]
        out = ({"decisions": [{"outcome": "approved", "subject": "CT-1051", "instead_of": None, "applies_to": ["BCU-24 Rev A"],
                               "summary": "Build BO-0415 from CT-1051 stock", "reason": "stock on hand", "decided_by": "Hithesh",
                               "decided_at": "2026-10-17", "ref": None,
                               "evidence": [{"chunk_id": p0, "quote": "we build BO-0415 on the 10th using the CT-1051 units in stock"}]},
                              {"outcome": "rejected", "subject": "NB54361-L", "instead_of": "NB54360", "applies_to": [],
                               "summary": "Invented", "reason": "x", "decided_by": "Hithesh", "decided_at": "2026-10-17", "ref": None,
                               "evidence": [{"chunk_id": p0, "quote": "words nobody said"}]}]}
               if kind == "decisions" else
               {"actions": [{"owner": "Ambika", "task": "Request quotes for CT-1051", "due": "Monday", "chunk_id": p1,
                             "quote": "I will request quotes for CT-1051 by Monday"}]})
        return {"source_id": source_id, "kind": kind, "model": "test-input", "extracted_at": "2026-10-17T00:00:00+00:00",
                "source_versions": [source_id], "output": out}
    monkeypatch.setattr(extract, "run_model", fake_model)
    mid = meetings.start(fresh_graph, "sync.m4a", b"not really audio", "BO-0415 sync", "Hithesh")
    for _ in range(100):
        if (meetings.status(mid) or {}).get("stage") in ("done", "failed"):
            break
        time.sleep(0.1)
    assert meetings.status(mid)["stage"] == "done", meetings.status(mid)
    m = meetings.get(fresh_graph, mid)
    assert [p["start"] for p in m["passages"]] == [0.0, 6.5]
    assert len(m["decisions"]) == 1 and m["decisions"][0]["subject"] == "CT-1051"   # the invented one is dropped
    assert m["actions"][0]["owner"] == "Ambika" and m["actions"][0]["at"] == 6.5
    assert meetings.status(mid)["result"]["rejected"] == 1
    hits = fresh_graph.query("CALL db.idx.fulltext.queryNodes('Chunk', 'request quotes') YIELD node RETURN node.id").result_set
    assert any(h[0].startswith(f"meetings/{mid}") for h in hits)                     # searchable company knowledge
    assert meetings.audio_path(mid) and meetings.audio_path("../../etc/passwd") is None
