"""Tests for the verification layer. The model outputs below are hand-written test inputs, not model results."""

from datetime import date
from decimal import Decimal

from neura1.impact import ChangeEvent, analyse
from neura1.ingest.extract import load_decisions, verify_notice

SLACK = "chats/slack_hw-power_2025-03.json"

GOOD = {
    "outcome": "rejected", "subject": "NB54361-L", "instead_of": "NB54360", "applies_to": ["PSU-24 Rev 2"],
    "summary": "NB54361-L rejected as substitute for NB54360 on PSU-24 Rev 2",
    "reason": "Fails thermal derating at 70C ambient in sealed cabinets", "decided_by": "Arjun Mehta",
    "decided_at": "2025-03-12", "ref": "DEC-117",
    "evidence": [{"chunk_id": f"{SLACK}#m4",
                  "quote": "we reject NB54361-L as a substitute for NB54360 on PSU-24 Rev 2"}],
}
INVENTED_QUOTE = {**GOOD, "ref": "DEC-999", "evidence": [
    {"chunk_id": f"{SLACK}#m4", "quote": "NB54361-L is approved for all products"}]}
UNKNOWN_PART = {**GOOD, "ref": "DEC-998", "subject": "ZZ9999"}


def snapshot(decisions):
    return {"source_id": SLACK, "model": "test-input", "extracted_at": "2026-10-16T00:00:00+00:00",
            "output": {"decisions": decisions}}


def test_unverifiable_decisions_are_not_written(graph):
    result = load_decisions(graph, snapshot([INVENTED_QUOTE, UNKNOWN_PART]))
    assert result["written"] == []
    assert len(result["rejected"]) == 2


def test_verified_rejection_flags_the_cheap_alternate(graph):
    result = load_decisions(graph, snapshot([GOOD]))
    assert result["written"] == ["DEC-117"]
    report = analyse(graph, ChangeEvent("NB54360", Decimal(320), "INR", None, 22, date(2026, 10, 16)))
    alt = {a["id"]: a for a in report["alternates"]}
    assert alt["NB54361-L"]["status"] == "rejected"
    assert alt["MX-3360"]["status"] == "unqualified"
    d = alt["NB54361-L"]["decisions"][0]
    assert d["decided_by"] == "Arjun Mehta" and d["applies_to"] == ["PSU-24-2"]
    assert d["authority"] == "extracted"
    # Loading the same decision again does not duplicate it
    load_decisions(graph, snapshot([GOOD]))
    assert len(analyse(graph, ChangeEvent("NB54360", Decimal(320), "INR", None, 22,
                                          date(2026, 10, 16)))["decisions"]) == 1


def test_notice_numbers_must_appear_in_text():
    text = "New unit price: ₹320 (previously ₹250). Standard lead time: 22 weeks. effective 2026-11-01"
    ok = {"new_unit_price": 320, "lead_weeks": 22, "effective_date": "2026-11-01"}
    assert verify_notice(ok, text) == []
    assert verify_notice({**ok, "new_unit_price": 330}, text) == ["new_unit_price=330 not found in notice text"]


def test_currency_symbols_map_to_iso_codes():
    from neura1.ingest.extract import normalise_currency
    assert normalise_currency("₹") == "INR" and normalise_currency("Rs.") == "INR"
    assert normalise_currency("$") == "USD" and normalise_currency(None) is None


def test_only_decision_style_refs_become_decision_ids(graph):
    bench = {**GOOD, "outcome": "evidence_only", "ref": "TR-131"}
    result = load_decisions(graph, snapshot([bench]))
    assert result["written"] and result["written"][0].startswith("DX-")
