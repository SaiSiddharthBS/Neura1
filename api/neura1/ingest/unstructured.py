"""Load chats, tickets, and documents as Source -> Chunk passages, with deterministic links.

No model is involved here. A chunk is linked to an entity only when it names that entity's
exact identifier (part number, revision, order id, person name, document reference). Decision
extraction, which does need a model, lives in `extract.py` and builds on these chunks.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from falkordb import Graph

from neura1.config import settings
from neura1.graph import rows

UNSTRUCTURED_DIRS = ("chats", "tickets", "docs", "inbox")
DOC_REF = re.compile(r"^([A-Z]{2,4}-[A-Z]{0,4}-?\d{2,4})")  # TR-112, HB-ENG-04, TP-PSU-07, HW-311


@dataclass
class Segment:
    key: str
    text: str
    author: str | None = None
    ts: str | None = None
    page: int | None = None


def _slack(data: dict) -> list[Segment]:
    return [Segment(m["id"], m["text"], m["user"], m["ts"]) for m in data["messages"]]


def _slack_dayfile(messages: list[dict]) -> list[Segment]:
    """A real Slack export day file: a JSON list of messages with user_profile.real_name."""
    segs = []
    for m in messages:
        if m.get("type", "message") != "message" or not m.get("text"):
            continue
        who = (m.get("user_profile") or {}).get("real_name") or m.get("user_name") or m.get("user")
        ts = m.get("ts")
        try:
            ts = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            pass
        segs.append(Segment(str(m.get("client_msg_id") or m.get("ts")), m["text"], who, ts))
    return segs


def _pdf(path: Path) -> list[Segment]:
    from pypdf import PdfReader

    segs = []
    for page_no, page in enumerate(PdfReader(path).pages, 1):
        for i, block in enumerate(re.split(r"\n\s*\n", page.extract_text() or "")):
            block = re.sub(r"[ \t]+", " ", block).strip()
            if block:
                segs.append(Segment(f"pg{page_no}-{i}", block, page=page_no))
    return segs


def _ticket(data: dict) -> list[Segment]:
    segs = [Segment("title", data["title"], data.get("reporter"), data.get("created")),
            Segment("description", data["description"], data.get("reporter"), data.get("created"))]
    for i, c in enumerate(data.get("comments", []), 1):
        segs.append(Segment(f"comment-{i}", c["body"], c["author"], c["date"]))
    return segs


def _markdown(text: str) -> list[Segment]:
    """Split on blank lines; track `--- Page N ---` markers so evidence can cite a page.

    A `Date: YYYY-MM-DD` line (as in notices and reports) dates every passage of the document.
    """
    found = re.search(r"^(?:Date|Prepared[^\n]*Date):?\s*.*?(\d{4}-\d{2}-\d{2})", text, re.M)
    dated = found.group(1) if found else None
    segs, page = [], None
    for i, block in enumerate(re.split(r"\n\s*\n", text)):
        block = block.strip()
        if not block:
            continue
        if m := re.fullmatch(r"--- Page (\d+) ---", block):
            page = int(m.group(1))
            continue
        segs.append(Segment(f"p{i}", block, ts=dated, page=page))
    return segs


SUPPORTED = (".json", ".md", ".txt", ".pdf")


def parse_source(path: Path, root: Path) -> tuple[dict, list[Segment]]:
    blob = path.read_bytes()
    rel = str(path.relative_to(root))
    ref_match = DOC_REF.match(path.stem)
    meta = {
        "id": rel,
        "uri": rel,
        "version": hashlib.sha256(blob).hexdigest()[:12],
        "ref": ref_match.group(1) if ref_match else None,
    }
    if path.suffix == ".pdf":
        meta |= {"kind": "notice" if path.parts[-2] == "inbox" else "doc", "title": path.stem.replace("_", " ")}
        return meta, _pdf(path)
    raw = blob.decode("utf-8", errors="replace")
    if path.suffix == ".json":
        data = json.loads(raw)
        if isinstance(data, list):
            meta |= {"kind": "chat", "title": f"Slack {path.parent.name or path.stem}"}
            return meta, _slack_dayfile(data)
        if "messages" in data:
            meta |= {"kind": "chat", "title": f"Slack {data['channel']}"}
            return meta, _slack(data)
        meta |= {"kind": "ticket", "title": f"{data['key']}: {data['title']}", "ref": data["key"],
                 "status": data.get("status")}
        return meta, _ticket(data)
    title = raw.splitlines()[0].lstrip("# ").strip()
    meta |= {"kind": "notice" if path.parts[-2] == "inbox" else "doc", "title": title}
    return meta, _markdown(raw)


def entity_lexicon(graph: Graph) -> list[tuple[re.Pattern, str]]:
    """Exact identifiers already in the graph, longest first, matched on token boundaries."""
    terms: dict[str, str] = {}
    for r in rows(graph, "MATCH (i:Item) RETURN i.id AS id, i.mpn AS mpn"):
        terms[r["id"]] = r["id"]
        if r["mpn"]:
            terms[r["mpn"]] = r["id"]
    for label, prop in (("Person", "name"), ("Customer", "name"), ("Build", "id"), ("Order", "id"),
                        ("Customer", "id"), ("Revision", "id"), ("Quote", "id")):
        for r in rows(graph, f"MATCH (n:{label}) RETURN n.id AS id, n.{prop} AS term"):
            terms[r["term"]] = r["id"]
    for r in rows(graph, "MATCH (s:Supplier) RETURN s.id AS id, s.name AS name"):
        terms[r["name"].split(" (")[0]] = r["id"]
    for r in rows(graph, "MATCH (p:Project) RETURN p.id AS id, p.name AS name"):
        terms[r["id"]] = r["id"]
        terms[r["name"]] = r["id"]
    for r in rows(graph, "MATCH (a:Alias)-[:REFERS_TO]->(x) RETURN a.term AS term, x.id AS id"):
        terms.setdefault(r["term"], r["id"])
    for r in rows(graph, "MATCH (s:Source) WHERE s.ref IS NOT NULL RETURN s.id AS id, s.ref AS ref"):
        terms.setdefault(r["ref"], r["id"])
    return [(re.compile(rf"(?<![\w-]){re.escape(t)}(?![\w-])"), target)
            for t, target in sorted(terms.items(), key=lambda kv: -len(kv[0]))]


REV_PHRASE = re.compile(r"\b([A-Z]{2,3}-\d{2,3}) Rev ([A-Z0-9])\b")


def mentions(text: str, lexicon: list[tuple[re.Pattern, str]]) -> set[str]:
    found = {target for pattern, target in lexicon if pattern.search(text)}
    # "VC-200 Rev C" names the revision VC-200-C
    found |= {f"{item}-{rev}" for item, rev in REV_PHRASE.findall(text)}
    return found


def load_sources(graph: Graph, root: Path | None = None, dirs=UNSTRUCTURED_DIRS,
                 files: list[Path] | None = None) -> dict[str, int]:
    root = root or settings.fixture_dir
    paths = files or sorted(p for d in dirs for p in (root / d).glob("*") if p.suffix in SUPPORTED)
    parsed = [(p, *parse_source(p, root)) for p in paths]

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Sources first, so cross-document references (TR-112, HW-311...) resolve on the second pass.
    # A changed file keeps its previous version id, so "what changed" can say when and from what.
    for _, meta, _ in parsed:
        graph.query("""
            MERGE (s:Source {id:$m.id})
            ON CREATE SET s.first_seen=$now
            SET s.previous_version = CASE WHEN s.version IS NOT NULL AND s.version <> $m.version
                                          THEN s.version ELSE s.previous_version END,
                s.updated_at = CASE WHEN s.version IS NULL OR s.version <> $m.version THEN $now ELSE s.updated_at END
            SET s += $m, s.authority='source_document'
        """, {"m": meta, "now": now})
    try:
        graph.query("CALL db.idx.fulltext.createNodeIndex('Chunk', 'text')")
    except Exception as exc:
        if "already" not in str(exc).lower():
            raise

    lexicon = entity_lexicon(graph)
    counts: dict[str, int] = {}
    for _, meta, segments in parsed:
        keep = []
        for ordinal, seg in enumerate(segments):
            chunk = {"id": f"{meta['id']}#{seg.key}", "text": seg.text, "author": seg.author, "ts": seg.ts,
                     "page": seg.page, "ordinal": ordinal, "source_version": meta["version"],
                     "text_hash": hashlib.sha256(seg.text.encode()).hexdigest()[:12]}
            keep.append(chunk["id"])
            # Passages are updated in place, so decisions and tasks that cite them keep their links,
            # and a changed passage is detectable by its text hash.
            graph.query("""
                MATCH (s:Source {id:$sid})
                MERGE (c:Chunk {id:$c.id})
                ON CREATE SET c.first_seen=$now
                SET c.revised_at = CASE WHEN c.text_hash IS NOT NULL AND c.text_hash <> $c.text_hash
                                        THEN $now ELSE c.revised_at END
                SET c += $c
                REMOVE c.retracted_at
                MERGE (c)-[:PART_OF]->(s)
                WITH c OPTIONAL MATCH (c)-[old:SAID_BY|MENTIONS]->() DELETE old
                WITH DISTINCT c OPTIONAL MATCH (p:Person {name:$c.author})
                FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (c)-[:SAID_BY]->(p))
            """, {"sid": meta["id"], "c": chunk, "now": now})
            targets = sorted(mentions(seg.text, lexicon) - {meta["id"]})
            if targets:
                graph.query("""
                    MATCH (c:Chunk {id:$cid}) UNWIND $targets AS t
                    MATCH (x {id:t}) MERGE (c)-[:MENTIONS]->(x)
                """, {"cid": chunk["id"], "targets": targets})
        # Passages that disappeared: delete them unless something cites them; then keep them, marked retracted.
        graph.query("""
            MATCH (s:Source {id:$sid})<-[:PART_OF]-(c:Chunk) WHERE NOT c.id IN $keep
            OPTIONAL MATCH (c)<-[cite:EVIDENCED_BY|CITES]-()
            WITH c, count(cite) AS cited
            FOREACH (_ IN CASE WHEN cited = 0 THEN [1] ELSE [] END | DETACH DELETE c)
            FOREACH (_ IN CASE WHEN cited > 0 THEN [1] ELSE [] END | SET c.retracted_at = $now)
        """, {"sid": meta["id"], "keep": keep, "now": now})
        counts[meta["id"]] = len(segments)
    return counts
