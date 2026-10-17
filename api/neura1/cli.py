"""Rebuild the demo graph from the fixture.

  uv run python -m neura1.cli load       # records + documents + saved extraction snapshots
  uv run python -m neura1.cli extract    # call the model on every document and save snapshots
  uv run python -m neura1.cli seed       # load the demo company only if the graph is empty
  uv run python -m neura1.cli check-model  # verify the model endpoint supports what Neura1 needs
  uv run python -m neura1.cli embed      # embed passages for semantic search (needs NEURA1_LLM_EMBED_MODEL)
  uv run python -m neura1.cli tag-skills # tag tasks and projects with the skills they need (model, verified)
"""

import json
import sys

from neura1.graph import get_graph
from neura1.ingest import extract
from neura1.ingest.structured import load_records
from neura1.ingest.unstructured import load_sources


def load(reset: bool = True) -> None:
    graph = get_graph()
    if reset:
        try:
            graph.delete()
        except Exception:
            pass
        graph = get_graph()
    print("records:", load_records(graph))
    print("sources:", load_sources(graph))
    print("decisions:", extract.load_snapshots(graph))
    from neura1 import capabilities
    print("skill tags:", capabilities.load_tags(graph))
    from neura1.config import settings
    if settings.llm_embed_model:
        try:
            from neura1.search import index_embeddings
            print("embedded passages:", index_embeddings(graph))
        except Exception as exc:  # semantic search stays off; keyword search still works
            print("embeddings skipped:", exc)


def extract_all(only: str | None = None) -> None:
    """Run the model over the demo documents, including the mid-demo updates, and snapshot the raw output.

    Update documents are loaded into a temporary graph so the main graph is not changed.
    """
    from neura1.config import settings
    from neura1.graph import rows

    graph = get_graph()
    jobs = [(graph, r["id"], "decisions") for r in rows(graph, """
        MATCH (s:Source) WHERE s.kind IN ['chat','ticket','doc'] AND NOT s.id STARTS WITH 'uploads/' AND NOT s.id STARTS WITH 'documents/'
              AND NOT s.id STARTS WITH 'chat/'
        RETURN s.id AS id ORDER BY id""")]
    jobs += [(graph, r["id"], "notice") for r in rows(graph, """
        MATCH (s:Source {kind:'notice'}) WHERE NOT s.id STARTS WITH 'uploads/' RETURN s.id AS id""")]

    scratch = get_graph(f"{settings.graph_name}_updates_scratch")
    try:
        scratch.delete()
    except Exception:
        pass
    scratch = get_graph(f"{settings.graph_name}_updates_scratch")
    load_records(scratch)
    updates = sorted(p for p in (settings.fixture_dir / "updates").glob("*") if p.suffix in (".json", ".md"))
    load_sources(scratch, files=updates)
    jobs += [(scratch, str(p.relative_to(settings.fixture_dir)), "decisions") for p in updates]

    jobs += [(graph, r["id"], "actions") for r in rows(graph, """
        MATCH (s:Source {kind:'doc'}) WHERE toLower(s.title) CONTAINS 'weekly' OR toLower(s.title) CONTAINS 'review'
              OR toLower(s.title) CONTAINS 'kickoff' RETURN s.id AS id""")]
    wanted = [w for w in (only or "").split(",") if w]
    if wanted:  # run in the order given, so the most important documents finish first
        jobs = [j for w in wanted for j in jobs if w in j[1]]
    for g, sid, kind in jobs:
        snap = extract.run_model(g, sid, kind)
        print(f"{kind:9} {sid}: {json.dumps(snap['output'], ensure_ascii=False)[:300]}", flush=True)
    if not only:
        print("tip: meeting action items are extracted with kind 'actions'", flush=True)
    scratch.delete()


def tag_skills() -> None:
    """Have the model tag each task and project with the skills it needs (from Flyvi's list only), then snapshot."""
    from neura1 import capabilities
    graph = get_graph()
    snap = capabilities.tag_with_model(graph)
    print(f"tagged {len(snap['tags'])} records with {snap['model']}; rejected: {snap['rejected'] or 'none'}")
    print("applied:", capabilities.load_tags(graph))


def embed() -> None:
    from neura1.search import index_embeddings
    print("embedded passages:", index_embeddings(get_graph()))


def seed() -> None:
    graph = get_graph()
    try:
        n = graph.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
    except Exception:
        n = 0
    if n:
        print(f"graph already has {n} nodes; not seeding")
    else:
        load(reset=False)


def check_model() -> None:
    """Three checks: plain chat, JSON-schema output, tool calling."""
    import json
    import time

    from neura1.config import settings
    from neura1.llm import chat_json, client

    c = client()
    print(f"endpoint {settings.llm_base_url}  model {settings.llm_model}")
    t = time.perf_counter()
    r = c.chat.completions.create(model=settings.llm_model, temperature=0,
                                  messages=[{"role": "user", "content": "Reply with the single word: ready"}])
    print(f"[chat]  {(r.choices[0].message.content or '').strip()[:60]!r}  {time.perf_counter() - t:.1f}s")
    t = time.perf_counter()
    out = chat_json("Extract fields as JSON.", "New unit price: ₹320, lead time 22 weeks.",
                    {"type": "object", "properties": {"price": {"type": "number"}, "weeks": {"type": "integer"}},
                     "required": ["price", "weeks"]}, "probe")
    print(f"[json]  {out}  {'OK' if out.get('price') == 320 and out.get('weeks') == 22 else 'WRONG'}  "
          f"{time.perf_counter() - t:.1f}s")
    t = time.perf_counter()
    try:
        r = c.chat.completions.create(model=settings.llm_model, temperature=0, messages=[
            {"role": "user", "content": "Who owns item FW-PMIC-SEQ? Use the tool."}], tools=[{
                "type": "function", "function": {"name": "who", "description": "Find the owner of an item id",
                                                 "parameters": {"type": "object", "properties": {
                                                     "text": {"type": "string"}}, "required": ["text"]}}}])
        calls = r.choices[0].message.tool_calls or []
        print(f"[tools] {[(x.function.name, json.loads(x.function.arguments)) for x in calls] or 'NO TOOL CALL'}  "
              f"{time.perf_counter() - t:.1f}s")
    except Exception as exc:
        print(f"[tools] FAILED: {exc}. For vLLM, start with --enable-auto-tool-choice --tool-call-parser <parser>")


if __name__ == "__main__":
    cmd, rest = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if cmd == "extract":
        extract_all(rest[0] if rest else None)
    else:
        {"load": load, "seed": seed, "check-model": check_model, "embed": embed,
         "tag-skills": tag_skills}.get(cmd, lambda: print(__doc__))()
