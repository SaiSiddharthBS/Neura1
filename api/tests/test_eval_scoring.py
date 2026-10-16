from eval.run_eval import corpus, rag_retrieve, score


def test_scoring_handles_numbers_groups_and_forbidden():
    case = {"all": ["37400"], "any": [["rejected", "no"]], "none": ["approved"]}
    assert score(case, "No. Increase is ₹37,400.")[0]
    assert not score(case, "Increase is ₹37,400 and it is approved")[0]
    assert not score({"all": ["420"]}, "We need 480")[0]


def test_baseline_corpus_contains_records_and_passages(graph, monkeypatch):
    docs = corpus(graph)
    assert any(d["id"].startswith("records/bom.csv") for d in docs)
    assert any("#m4" in d["id"] for d in docs)
    hits = rag_retrieve(docs, "Who decided against NB54361-L?")
    assert len(hits) == 8
