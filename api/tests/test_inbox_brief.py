"""Neura1 acts on its own: emails dropped in the inbox become signals, and a morning brief is posted once a day."""

from datetime import date
from email.message import EmailMessage

from neura1 import brief, inbox
from neura1.config import settings
from neura1.graph import rows
from neura1.llm import LLMUnavailable


def _eml(subject: str, body: str) -> bytes:
    m = EmailMessage()
    m["Subject"], m["From"], m["Date"] = subject, "sales@deccan.example", "Fri, 16 Oct 2026 10:00:00 +0530"
    m.set_content(body)
    return bytes(m)


def test_emails_are_read_and_classified():
    m = inbox.parse_email(_eml("PCN: NB54360 price and lead-time change", "New price from 1 Nov; lead time 22 weeks."))
    assert m["date"] == "2026-10-16" and "22 weeks" in m["body"]
    assert inbox.classify(m["subject"], m["body"]) == "notice"
    assert inbox.classify("Urgent: telemetry failures at our site", "We may hold acceptance of SO-884.") == "escalation"
    assert inbox.classify("Leave request", "I will be away from 2 to 27 November.") == "leave"


def test_a_dropped_email_becomes_a_signal(fresh_graph, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from neura1.ingest import extract
    monkeypatch.setattr(extract, "run_model", lambda *a, **k: (_ for _ in ()).throw(LLMUnavailable("no model in tests")))
    (inbox.drop_dir() / "fwd.eml").write_bytes(_eml("Escalation: BCU-24 telemetry at Konkan Naval",
                                                    "Konkan Naval Electronics may hold acceptance of SO-884."))
    done = inbox.process_drop(fresh_graph)
    assert done and done[0]["kind"] == "escalation" and "error" not in done[0]
    assert rows(fresh_graph, "MATCH (s:Source {kind:'escalation'}) WHERE s.id STARTS WITH 'uploads/' RETURN count(s) AS n")[0]["n"] == 1
    assert not list(inbox.drop_dir().glob("*.eml")) and list((inbox.drop_dir() / "processed").iterdir())


def test_morning_brief_is_safe_for_everyone_and_posted_once(fresh_graph):
    b = brief.compose(fresh_graph, date(2026, 10, 30))
    assert "signal" in b["text"] and "₹" not in b["text"]
    assert "Raghavendra" not in b["text"]  # leave is a count, never a name, in #general
    assert brief.post(fresh_graph, date(2026, 10, 30)) is not None
    assert brief.post(fresh_graph, date(2026, 10, 30)) is None
    posts = rows(fresh_graph, "MATCH (c:Chunk {kind:'brief'})-[:PART_OF]->(:Source {id:'chat/general'}) RETURN count(c) AS n")
    assert posts[0]["n"] == 1


def test_a_notice_part_written_with_its_description_maps_to_the_item(fresh_graph):
    from neura1.ingest import extract
    assert extract.resolve_part(fresh_graph, "CT-1051 CAN transceiver") == "CT-1051"
    assert extract.resolve_part(fresh_graph, "NB54360") == "NB54360"
    assert extract.resolve_part(fresh_graph, "NB54360 or NB54361-L") is None  # ambiguous: never guessed
    snap = extract.with_resolved_part(fresh_graph, {"output": {"part": "CT-1051 CAN transceiver"}})
    assert snap["output"]["part"] == "CT-1051" and snap["output"]["part_as_written"] == "CT-1051 CAN transceiver"
