"""Score answer systems on the frozen golden set.

  uv run python -m eval.run_eval --system graph      # Neura1 agent with graph tools
  uv run python -m eval.run_eval --system rag        # top-k full-text retrieval over the same corpus + same model
  uv run python -m eval.run_eval --system context    # whole corpus in the prompt + same model

All three systems see the same company data and use the same model. Results go to eval/results/.
"""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from neura1.config import settings
from neura1.graph import get_graph, rows
from neura1.ingest.structured import read_csv
from neura1.llm import client

HERE = Path(__file__).parent


def normalise(text: str) -> str:
    return re.sub(r"(?<=\d),(?=\d)", "", text.replace("₹", "")).lower()


def score(case: dict, answer: str) -> tuple[bool, list[str]]:
    a = normalise(answer)
    missing = [s for s in case.get("all", []) if normalise(str(s)) not in a]
    missing += [f"one of {group}" for group in case.get("any", [])
                if not any(normalise(str(s)) in a for s in group)]
    # Forbidden text is checked against the raw answer: normalising would turn a forbidden "₹" into "", which matches
    # every answer (fixed 2026-10-17; before this, abstain questions with "none: [₹]" could never pass).
    raw = answer.lower()
    forbidden = [s for s in case.get("none", []) if str(s).lower() in raw]
    return not missing and not forbidden, missing + [f"forbidden {s}" for s in forbidden]


# ---------- baselines ----------

def corpus(graph, updated: bool = False) -> list[dict]:
    """The same knowledge the graph holds, flattened to text: every CSV row and every passage."""
    docs = []
    paths = sorted((settings.fixture_dir / "records").glob("*.csv"))
    if updated:
        paths += sorted((settings.fixture_dir / "updates").glob("*.csv"))
    for path in paths:
        for i, r in enumerate(read_csv(path)):
            docs.append({"id": f"records/{path.name}#{i}",
                         "text": f"{path.stem} record: " + ", ".join(f"{k}={v}" for k, v in r.items() if v)})
    for r in rows(graph, "MATCH (c:Chunk)-[:PART_OF]->(s:Source) RETURN c.id AS id, s.title AS title, "
                         "c.author AS author, c.ts AS ts, c.page AS page, c.text AS text"):
        meta = ", ".join(str(r[k]) for k in ("author", "ts") if r[k]) + (f", page {r['page']}" if r["page"] else "")
        docs.append({"id": r["id"], "text": f"[{r['title']}{'; ' + meta if meta else ''}] {r['text']}"})
    return docs


BASELINE_SYSTEM = ("You answer questions about Flyvi Technologies using ONLY the provided company records and "
                   "documents. If the answer is not in them, say it is not recorded. Be concise and cite ids.")


def answer_with_context(question: str, docs: list[dict]) -> str:
    ctx = "\n".join(d["text"] for d in docs)
    resp = client().chat.completions.create(model=settings.llm_model, temperature=0, messages=[
        {"role": "system", "content": BASELINE_SYSTEM},
        {"role": "user", "content": f"Company data:\n{ctx}\n\nQuestion: {question}"}])
    return re.sub(r"^.*?</think>", "", resp.choices[0].message.content or "", flags=re.S).strip()


def rag_retrieve(docs: list[dict], question: str, k: int = 8) -> list[dict]:
    """Plain lexical retrieval (term overlap weighted by rarity) so the baseline has no graph help."""
    tokens = lambda s: set(re.findall(r"[a-z0-9][a-z0-9\-\.]+", s.lower()))
    doc_tokens = [tokens(d["text"]) for d in docs]
    df: dict[str, int] = {}
    for ts in doc_tokens:
        for t in ts:
            df[t] = df.get(t, 0) + 1
    q = tokens(question)
    scored = sorted(range(len(docs)), key=lambda i: -sum(1 / df[t] for t in q & doc_tokens[i]))
    return [docs[i] for i in scored[:k]]


# ---------- runner ----------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["graph", "rag", "context"], required=True)
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="all")
    ap.add_argument("--state", choices=["base", "updated"], default="base")
    args = ap.parse_args()

    cases = [c for c in yaml.safe_load((HERE / "golden.yaml").read_text())
             if c.get("state", "base") == args.state and (args.split == "all" or c["split"] == args.split)]
    graph = get_graph()
    docs = corpus(graph, args.state == "updated") if args.system != "graph" else []
    if args.system == "graph":
        from neura1.agent import ask

    results = []
    for c in cases:
        t0 = time.perf_counter()
        try:
            if args.system == "graph":
                out = ask(graph, c["question"])
                answer, extra = out["answer"], {"tool_calls": out["tool_calls"]}
            elif args.system == "rag":
                hits = rag_retrieve(docs, c["question"])
                answer, extra = answer_with_context(c["question"], hits), {"retrieved": [h["id"] for h in hits]}
            else:
                answer, extra = answer_with_context(c["question"], docs), {}
        except Exception as exc:
            answer, extra = f"ERROR: {exc}", {}
        ok, why = score(c, answer)
        results.append({"id": c["id"], "category": c["category"], "split": c["split"], "pass": ok, "missing": why,
                        "seconds": round(time.perf_counter() - t0, 2), "question": c["question"],
                        "answer": answer, **extra})
        print(f"{'PASS' if ok else 'FAIL'} {c['id']} {c['category']:24} {why if not ok else ''}")

    passed = sum(r["pass"] for r in results)
    print(f"\n{args.system}: {passed}/{len(results)} passed")
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    (out_dir / f"{args.system}-{args.state}-{args.split}-{stamp}.json").write_text(json.dumps(
        {"system": args.system, "model": settings.llm_model, "state": args.state, "split": args.split,
         "passed": passed, "total": len(results), "results": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
