"""Hybrid search: semantic (FalkorDB vector index) + keyword (full-text index), then expanded through the graph.

Results from both indexes are merged with reciprocal rank fusion. Each passage then brings the records it mentions,
so a search for "cold start problems" returns the passages and the parts, people and customers involved.
Without an embedding model the search is keyword-only and says so.
"""

from falkordb import Graph

from neura1.graph import rows
from neura1.llm import LLMUnavailable, embed

VECTOR = """
CALL db.idx.vector.queryNodes('Chunk', 'embedding', $k, vecf32($v)) YIELD node, score
RETURN node.id AS chunk, score
"""

KEYWORD = """
CALL db.idx.fulltext.queryNodes('Chunk', $q) YIELD node, score
RETURN node.id AS chunk, score LIMIT $k
"""

EXPAND = """
MATCH (c:Chunk) WHERE c.id IN $ids
MATCH (c)-[:PART_OF]->(s:Source)
OPTIONAL MATCH (c)-[:MENTIONS]->(x) WHERE NOT x:Source
RETURN c.id AS chunk, c.text AS text, c.author AS author, c.ts AS ts, c.page AS page, s.title AS title, s.kind AS kind,
       collect(DISTINCT {id: x.id, label: labels(x)[0]}) AS mentions
"""


def index_embeddings(graph: Graph, batch: int = 16) -> int:
    """Embed every passage that has no embedding yet and create the vector index."""
    todo = rows(graph, "MATCH (c:Chunk) WHERE c.embedding IS NULL RETURN c.id AS id, c.text AS text")
    done = 0
    dim = None
    for i in range(0, len(todo), batch):
        part = todo[i:i + batch]
        vectors = embed([p["text"][:2000] for p in part])
        dim = len(vectors[0])
        for p, v in zip(part, vectors):
            graph.query("MATCH (c:Chunk {id:$id}) SET c.embedding = vecf32($v)", {"id": p["id"], "v": v})
        done += len(part)
    if dim:
        try:
            graph.query(f"CREATE VECTOR INDEX FOR (c:Chunk) ON (c.embedding) "
                        f"OPTIONS {{dimension:{dim}, similarityFunction:'cosine'}}")
        except Exception as exc:
            if "already" not in str(exc).lower():
                raise
    return done


def hybrid(graph: Graph, q: str, k: int = 8) -> dict:
    ranked: dict[str, float] = {}
    modes = []
    try:
        for rank, r in enumerate(rows(graph, KEYWORD, {"q": q, "k": k * 2})):
            ranked[r["chunk"]] = ranked.get(r["chunk"], 0) + 1 / (60 + rank)
        modes.append("keyword")
    except Exception:
        pass
    try:
        v = embed([q])[0]
        for rank, r in enumerate(rows(graph, VECTOR, {"k": k * 2, "v": v})):
            ranked[r["chunk"]] = ranked.get(r["chunk"], 0) + 1 / (60 + rank)
        modes.append("semantic")
    except (LLMUnavailable, Exception):
        pass
    top = sorted(ranked, key=lambda c: -ranked[c])[:k]
    details = {r["chunk"]: r for r in rows(graph, EXPAND, {"ids": top})}
    hits = [details[c] | {"score": round(ranked[c], 4), "mentions": [m for m in details[c]["mentions"] if m.get("id")]}
            for c in top if c in details]
    related: dict[str, dict] = {}
    for h in hits:
        for m in h["mentions"]:
            related.setdefault(m["id"], m | {"passages": 0})["passages"] += 1
    return {"query": q, "modes": modes, "hits": hits,
            "related": sorted(related.values(), key=lambda m: -m["passages"])[:12]}
