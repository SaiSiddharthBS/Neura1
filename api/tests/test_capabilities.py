"""Capability map: verified skill tags, evidence from real work, and people analytics that respect who may see what."""

from neura1 import capabilities
from neura1.access import viewer


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _walk_keys(x)


def test_model_tags_are_limited_to_known_records_and_skills():
    kept, rejected = capabilities.verify_tags(
        [{"id": "WRK-106", "skills": ["embedded c", "Power sequencing", "Rocket science"]},
         {"id": "WRK-999", "skills": ["Embedded C"]}],
        ["Embedded C", "Power sequencing"], {"WRK-106"})
    assert kept == {"WRK-106": ["Embedded C", "Power sequencing"]}
    assert rejected == {"WRK-106": ["Rocket science"], "_unknown_records": ["WRK-999"]}


def test_expertise_comes_from_finished_work_with_its_evidence(fresh_graph):
    capabilities.load_tags(fresh_graph)
    e = capabilities.person_expertise(fresh_graph, "P-SAI", viewer(fresh_graph, "P-HITHESH"))
    seq = next(s for s in e["skills"] if s["skill"] == "Power sequencing")
    assert seq["level"] == "hands-on" and any(t["id"] == "WRK-106" for t in seq["finished"])


def test_a_colleague_sees_only_stated_skills(fresh_graph):
    capabilities.load_tags(fresh_graph)
    e = capabilities.person_expertise(fresh_graph, "P-SAI", viewer(fresh_graph, "P-ANIRUDH"))
    assert e["restricted"] and "skills" not in e and "Embedded C" in e["stated"]
    # The person, and their management chain, see it.
    assert not capabilities.person_expertise(fresh_graph, "P-SAI", viewer(fresh_graph, "P-SAI"))["restricted"]
    assert not capabilities.person_expertise(fresh_graph, "P-SAI", viewer(fresh_graph, "P-HITHESH"))["restricted"]


def test_company_map_shows_names_only_to_people_allowed_to_see_them(fresh_graph):
    capabilities.load_tags(fresh_graph)
    lead = capabilities.company_map(fresh_graph, viewer(fresh_graph, "P-HITHESH"))
    seq = next(s for s in lead["skills"] if s["skill"] == "Power sequencing")
    assert seq["status"] == "thin" and [p["name"] for p in seq["people"]] == ["Sai"]
    engineer = capabilities.company_map(fresh_graph, viewer(fresh_graph, "P-ANIRUDH"))
    assert engineer["visibility"] == "counts"
    assert {p["id"] for s in engineer["skills"] for p in s["people"]} <= {"P-ANIRUDH"}
    assert all(s["away_soon"] is None for s in engineer["skills"])


def test_no_scores_or_rankings_are_produced(fresh_graph):
    capabilities.load_tags(fresh_graph)
    out = [capabilities.company_map(fresh_graph, viewer(fresh_graph, "P-HITHESH")),
           capabilities.person_expertise(fresh_graph, "P-SAI", viewer(fresh_graph, "P-HITHESH"))]
    banned = {"score", "rank", "rating", "percent", "percentile"}
    assert not {k for k in _walk_keys(out) if any(b in k.lower() for b in banned)}
