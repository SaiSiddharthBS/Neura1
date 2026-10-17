"""Never the same mistake twice: a message or draft is checked against what Flyvi already knows while it is written.

The checks are the document fact checker's rules (no model): proposing a part the company rejected, calling an
unapproved alternate approved, an expired quote, an obsolete or draft revision, a price that matches no quote, or
giving work to someone who will be away. A rejected decision comes back with the passages that prove it, word for word,
so the writer sees why before anyone acts on it. Chat is looser than a formal document, so more phrasings count as
proposing a part ("let's try", "order", "go for", "swap to").
"""

import re
import threading
import time

from falkordb import Graph

from neura1 import documents
from neura1.access import Viewer
from neura1.graph import rows

CHAT_ADOPT = re.compile(documents.ADOPT.pattern[:-len(r")\b")] +
                        r"|try|trial|order|buy|procure|purchase|swap\w*|go for|pick|choose|consider|cheaper|"
                        r"alternative|instead|drop[- ]in|pin[- ]compatible)\b", re.I)

_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()
TTL = 15.0


def _facts(graph: Graph) -> dict:
    """The facts the checks need, reused for a few seconds: guard runs on every pause in typing."""
    key = graph.name
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    facts = documents._facts(graph)
    with _lock:
        _cache[key] = (time.time(), facts)
    return facts


def forget() -> None:
    """Drop cached facts (after a reset or a new decision)."""
    with _lock:
        _cache.clear()


def check(graph: Graph, text: str, viewer: Viewer) -> list[dict]:
    text = (text or "").strip()
    if len(text) < 4:
        return []
    flags = documents.check(graph, [{"id": "m", "text": text}], viewer, adopt=CHAT_ADOPT, facts=_facts(graph))
    sources = sorted({s for f in flags for s in f.get("sources") or []})
    passages = {r["id"]: r for r in rows(graph, """
        MATCH (c:Chunk)-[:PART_OF]->(s:Source) WHERE c.id IN $ids
        RETURN c.id AS id, s.id AS source, s.title AS title, s.kind AS kind, c.author AS author, c.ts AS ts,
               c.text AS text""", {"ids": sources})} if sources else {}
    order = {"error": 0, "warning": 1, "info": 2}
    out = []
    for f in sorted(flags, key=lambda x: order.get(x["severity"], 3)):
        out.append({k: f[k] for k in ("quote", "severity", "title", "message", "record")}
                   | {"evidence": [passages[s] for s in f.get("sources") or [] if s in passages]})
    return out


def reminder(flags: list[dict]) -> str | None:
    """What Neura1 says in a conversation when a message proposes something the company already rejected."""
    rejected = [f for f in flags if f["severity"] == "error"]
    if not rejected:
        return None
    lines = []
    for f in rejected[:2]:
        where = "; ".join(f"{e['title']}{' · ' + e['author'] if e.get('author') else ''}: “{_clip(e['text'])}”"
                          for e in f["evidence"][:2])
        lines.append(f"**{f['title']}**. {f['message']}" + (f"\n> {where}" if where else ""))
    return "Before this goes further, the company has been here before.\n\n" + "\n\n".join(lines)


def _clip(text: str, n: int = 160) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"
