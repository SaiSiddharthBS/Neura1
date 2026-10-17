"""Model-assisted extraction of decisions and supplier notices, with deterministic verification.

The model proposes; code verifies. A decision is written to the graph only if:
  * every evidence quote appears verbatim in the passage it cites, and
  * its subject resolves to exactly one known item.
Everything written here carries authority='extracted'. Nothing extracted can approve a part.

Results are snapshotted to fixture/<company>/extracted/ with the model name, so the demo and
the deployed site replay exactly what the model produced, and re-extraction is an explicit step.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from falkordb import Graph

from neura1 import queries as Q
from neura1 import llm as _llm
from neura1.config import settings
from neura1.graph import rows
from neura1.llm import chat_json

DECISION_SCHEMA = {
    "type": "object",
    "properties": {"decisions": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "outcome": {"type": "string", "enum": ["approved", "rejected", "proposed", "evidence_only"]},
            "subject": {"type": "string", "description": "Part number the decision is about, exactly as written"},
            "instead_of": {"type": ["string", "null"], "description": "Part it would replace, as written"},
            "applies_to": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
            "reason": {"type": ["string", "null"]},
            "decided_by": {"type": ["string", "null"], "description": "Person's full name as written"},
            "decided_at": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            "ref": {"type": ["string", "null"], "description": "Decision identifier if one is written, e.g. DEC-117"},
            "evidence": {"type": "array", "items": {"type": "object", "properties": {
                "chunk_id": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["chunk_id", "quote"]}},
        },
        "required": ["outcome", "subject", "instead_of", "applies_to", "summary", "reason", "decided_by",
                     "decided_at", "ref", "evidence"],
    }}},
    "required": ["decisions"],
}

DECISION_SYSTEM = """You extract engineering and sourcing decisions about specific parts from company records.
Rules:
- Only report what the passages state. If nothing was decided or tested about a part, return {"decisions": []}.
- outcome: "approved" or "rejected" only when a person states a decision; "proposed" for a suggestion;
  "evidence_only" for a test or bench result about a part that informs a decision but is not one.
  A test or bench result about a candidate part MUST be reported as "evidence_only", even if nobody decided yet.
- subject is the part being decided about (for a rejected substitute, the substitute). instead_of is the part
  it would have replaced.
- decided_by is the person who stated the decision; decided_at is the date of that passage (YYYY-MM-DD).
- ref is a decision id such as DEC-123 if one is written, else null.
- applies_to lists assemblies/products with revisions as written, e.g. "PSM-28 Rev 2".
- evidence: cite the passage that STATES the decision first, then any passage with the test result.
  chunk_id is the number in square brackets, e.g. "3". quote is copied EXACTLY from that passage and is
  one sentence or less.

Example (a different company):
[1] (author=Lee Wong, ts=2024-02-01T10:00:00)
Bench test of RX-12 failed ESD at 8 kV. See TR-9.
[2] (author=Sam Ortiz, ts=2024-02-03T09:00:00)
Decision: we will not use RX-12 instead of RX-10 on BRD-5 Rev A because it fails ESD (TR-9). Logged as DEC-4.
Output:
{"decisions": [{"outcome": "rejected", "subject": "RX-12", "instead_of": "RX-10", "applies_to": ["BRD-5 Rev A"],
 "summary": "RX-12 rejected as substitute for RX-10 on BRD-5 Rev A", "reason": "Fails ESD at 8 kV (TR-9)",
 "decided_by": "Sam Ortiz", "decided_at": "2024-02-03", "ref": "DEC-4",
 "evidence": [{"chunk_id": "2", "quote": "we will not use RX-12 instead of RX-10 on BRD-5 Rev A because it fails ESD (TR-9)"},
              {"chunk_id": "1", "quote": "Bench test of RX-12 failed ESD at 8 kV."}]}]}

Example of a test result with no decision:
[1] (author=Lee Wong, ts=2024-05-02T10:00:00)
RX-14 passed the ESD bench check at 8 kV on BRD-5 Rev A. Full qualification still pending.
Output:
{"decisions": [{"outcome": "evidence_only", "subject": "RX-14", "instead_of": null, "applies_to": ["BRD-5 Rev A"],
 "summary": "RX-14 passed ESD bench check on BRD-5 Rev A; full qualification pending", "reason": null,
 "decided_by": "Lee Wong", "decided_at": "2024-05-02", "ref": null,
 "evidence": [{"chunk_id": "1", "quote": "RX-14 passed the ESD bench check at 8 kV on BRD-5 Rev A."}]}]}"""

NOTICE_SCHEMA = {
    "type": "object",
    "properties": {
        "part": {"type": "string"},
        "change_types": {"type": "array", "items": {"type": "string",
                         "enum": ["price", "lead_time", "lifecycle", "moq", "other"]}},
        "new_unit_price": {"type": ["number", "null"]},
        "currency": {"type": ["string", "null"], "description": "ISO code, e.g. INR"},
        "effective_date": {"type": ["string", "null"]},
        "lead_weeks": {"type": ["integer", "null"]},
        "last_time_buy": {"type": ["string", "null"]},
        "supplier": {"type": ["string", "null"]},
    },
    "required": ["part", "change_types", "new_unit_price", "currency", "effective_date", "lead_weeks"],
}

ACTIONS_SCHEMA = {
    "type": "object",
    "properties": {"actions": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Person's name exactly as written"},
            "task": {"type": "string", "description": "What they will do, as a short imperative"},
            "due": {"type": ["string", "null"], "description": "YYYY-MM-DD if a date is written, else null"},
            "chunk_id": {"type": "string"},
            "quote": {"type": "string", "description": "Copied exactly from the passage"},
        },
        "required": ["owner", "task", "due", "chunk_id", "quote"],
    }}},
    "required": ["actions"],
}

ACTIONS_SYSTEM = """You read meeting notes and list the action items: things a named person said they will do or was
asked to do. Only include items with a clear owner. chunk_id is the number in square brackets of the passage.
quote is copied EXACTLY from that passage and shows the commitment. If there are no action items, return
{"actions": []}."""

NOTICE_SYSTEM = """You read supplier notices and return the changed facts as JSON. Use null when the notice
does not state a value. Never compute or infer prices or dates that are not written."""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def source_passages(graph: Graph, source_id: str) -> list[dict]:
    return rows(graph, """
        MATCH (c:Chunk)-[:PART_OF]->(:Source {id:$id})
        RETURN c.id AS id, c.text AS text, c.author AS author, c.ts AS ts, c.page AS page
        ORDER BY c.ordinal""", {"id": source_id})


def _prompt(passages: list[dict]) -> str:
    """Passages are numbered [1]..[n] for the model; `passage_ids` maps the numbers back."""
    lines = []
    for n, p in enumerate(passages, 1):
        meta = ", ".join(f"{k}={p[k]}" for k in ("author", "ts", "page") if p.get(k))
        lines.append(f"[{n}] ({meta})\n{p['text']}")
    return "\n\n".join(lines)


def resolve_chunk_ref(ref: str, passages: list[dict]) -> str | None:
    """Accept "3", "[3]", a full chunk id, or a bare segment key like "m4"."""
    ref = str(ref).strip().strip("[]")
    ids = [p["id"] for p in passages]
    if ref in ids:
        return ref
    if ref.isdigit() and 1 <= int(ref) <= len(ids):
        return ids[int(ref) - 1]
    matches = [i for i in ids if i.endswith("#" + ref)]
    return matches[0] if len(matches) == 1 else None


def snapshot_path(source_id: str, kind: str) -> Path:
    """Snapshots for the demo fixture live with the fixture; a company's own uploads live in data/."""
    safe = source_id.replace("/", "__")
    base = settings.fixture_dir if (settings.fixture_dir / source_id).is_file() else settings.data_dir
    return base / "extracted" / f"{safe}.{kind}.json"


def save_manual_notice(source_id: str, fields: dict, entered_by: str) -> dict:
    """A person typed the notice facts in. Stored like a model snapshot, and verified the same way."""
    snap = {"source_id": source_id, "kind": "notice", "model": f"entered by {entered_by}",
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "output": fields}
    path = snapshot_path(source_id, "notice")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2, ensure_ascii=False))
    return snap


def run_model(graph: Graph, source_id: str, kind: str, passages: list[dict] | None = None) -> dict:
    """Call the model and snapshot the raw output. Verification happens separately on load.
    `passages` narrows what the model reads (e.g. only people's messages in a chat channel)."""
    passages = passages if passages is not None else source_passages(graph, source_id)
    if kind == "decisions":
        out = chat_json(DECISION_SYSTEM, _prompt(passages), DECISION_SCHEMA, "decisions")
    elif kind == "actions":
        out = chat_json(ACTIONS_SYSTEM, _prompt(passages), ACTIONS_SCHEMA, "actions")
        for a in out.get("actions", []):
            a["chunk_id"] = resolve_chunk_ref(a.get("chunk_id", ""), passages) or a.get("chunk_id")
    else:
        out = chat_json(NOTICE_SYSTEM, "\n\n".join(p["text"] for p in passages), NOTICE_SCHEMA, "notice")
    if kind == "decisions":
        for d in out.get("decisions", []):
            for e in d.get("evidence", []):
                e["chunk_id"] = resolve_chunk_ref(e.get("chunk_id", ""), passages) or e.get("chunk_id")
    snap = {"source_id": source_id, "kind": kind, "model": _llm.last_model or settings.llm_model,
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_versions": sorted({p["id"].split("#")[0] for p in passages}), "output": out}
    path = snapshot_path(source_id, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2, ensure_ascii=False))
    return snap


# ---------- deterministic verification ----------

def verify_decision(d: dict, passages: dict[str, dict], resolve) -> tuple[dict | None, list[str]]:
    """Return (verified decision, problems). `resolve(text)` maps a part number to an item id or None."""
    problems = []
    evidence = []
    ordered = list(passages.values())
    for e in d.get("evidence", []):
        cid = resolve_chunk_ref(e.get("chunk_id", ""), ordered) or e.get("chunk_id")
        e = {**e, "chunk_id": cid}
        p = passages.get(cid)
        if p is None:
            problems.append(f"cites unknown passage {e['chunk_id']}")
        elif _norm(e["quote"]) and _norm(e["quote"]) in _norm(p["text"]):
            evidence.append(e)
        else:
            problems.append(f"quote not found verbatim in {e['chunk_id']}: {e['quote'][:80]!r}")
    if not evidence:
        return None, problems + ["no verifiable evidence"]
    subject = resolve(d["subject"])
    if subject is None:
        return None, problems + [f"subject {d['subject']!r} does not resolve to a known item"]
    instead_of = resolve(d["instead_of"]) if d.get("instead_of") else None
    ref = (d.get("ref") or "").strip().upper()
    # Only decision/change identifiers become ids; a test report number (TR-131) is not a decision id.
    key = ref if DECISION_REF.fullmatch(ref) else "DX-" + hashlib.sha256(
        f"{subject}|{instead_of}|{d['outcome']}".encode()).hexdigest()[:8]
    return {**d, "id": key, "subject_id": subject, "instead_of_id": instead_of, "evidence": evidence}, problems


CURRENCY = {"₹": "INR", "RS": "INR", "RS.": "INR", "INR": "INR", "$": "USD", "US$": "USD", "USD": "USD",
            "€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP"}


def normalise_currency(value: str | None) -> str | None:
    """Map what a notice or model writes (₹, Rs., $) to an ISO code; unknown values stay as written."""
    if not value:
        return None
    return CURRENCY.get(value.strip().upper(), value.strip().upper())


PART_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{3,}")


def resolve_part(graph: Graph, written: str | None) -> str | None:
    """The part a notice means, as a known item id. Models sometimes write the part with its description
    ("CT-1051 CAN transceiver"); this maps that to the one item it names, or returns None when it is ambiguous."""
    if not written:
        return None
    exact = rows(graph, Q.RESOLVE_ITEM, {"text": written.strip()})
    if len(exact) == 1:
        return exact[0]["id"]
    hits = {r["id"] for t in PART_TOKEN.findall(written) for r in rows(graph, Q.RESOLVE_ITEM, {"text": t})}
    return hits.pop() if len(hits) == 1 else None


def with_resolved_part(graph: Graph, snap: dict) -> dict:
    """The snapshot as consumers should see it: the raw model output stays in the file; the part is mapped to its id
    (and the model's wording kept as part_as_written)."""
    out = dict(snap.get("output") or {})
    pid = resolve_part(graph, out.get("part"))
    if pid and pid != out.get("part"):
        out["part_as_written"], out["part"] = out.get("part"), pid
    return snap | {"output": out}


def verify_notice(n: dict, text: str) -> list[str]:
    """Every number the model reports must appear in the notice text."""
    problems = []
    for field in ("new_unit_price", "lead_weeks"):
        v = n.get(field)
        if v is not None and not re.search(rf"(?<!\d){re.escape(str(int(v)) if float(v).is_integer() else str(v))}(?!\d)", text):
            problems.append(f"{field}={v} not found in notice text")
    for field in ("effective_date", "last_time_buy"):
        if n.get(field) and n[field] not in text:
            problems.append(f"{field}={n[field]} not found in notice text")
    return problems


DECISION_REF = re.compile(r"(DEC|ECO|ECN|ECR|DCN|DCR)-\d+")
REV_TEXT = re.compile(r"\b([A-Z]{2,3}-\d{2,3}) Rev ([A-Z0-9])\b")


def load_decisions(graph: Graph, snapshot: dict) -> dict:
    passages = {p["id"]: p for p in source_passages(graph, snapshot["source_id"])}

    def resolve(text):
        found = rows(graph, Q.RESOLVE_ITEM, {"text": text.strip()})
        return found[0]["id"] if len(found) == 1 else None

    written, rejected = [], []
    for raw in snapshot["output"].get("decisions", []):
        d, problems = verify_decision(raw, passages, resolve)
        if d is None:
            rejected.append({"decision": raw, "problems": problems})
            continue
        revs = [f"{a}-{b}" for t in d.get("applies_to", []) for a, b in REV_TEXT.findall(t)]
        outcome = "evidence" if d["outcome"] == "evidence_only" else d["outcome"]
        graph.query("""
            MERGE (d:Decision {id:$id})
            SET d.outcome=$outcome, d.summary=$summary, d.reason=$reason, d.decided_at=$decided_at,
                d.authority='extracted', d.status=coalesce(d.status, 'active'),
                d.extracted_by=$model, d.extracted_at=$at
            WITH d MATCH (s:Item {id:$subject}) MERGE (d)-[:ABOUT]->(s)
            WITH d OPTIONAL MATCH (i:Item {id:$instead_of})
            FOREACH (_ IN CASE WHEN i IS NULL THEN [] ELSE [1] END | MERGE (d)-[:INSTEAD_OF]->(i))
            WITH d OPTIONAL MATCH (p:Person {name:$by})
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (d)-[:DECIDED_BY]->(p))
            WITH d UNWIND (CASE WHEN size($revs) = 0 THEN [NULL] ELSE $revs END) AS rid
            OPTIONAL MATCH (r:Revision {id:rid})
            FOREACH (_ IN CASE WHEN r IS NULL THEN [] ELSE [1] END | MERGE (d)-[:APPLIES_TO]->(r))
        """, {"id": d["id"], "outcome": outcome, "summary": d["summary"], "reason": d.get("reason"),
              "decided_at": d.get("decided_at"), "model": snapshot["model"], "at": snapshot["extracted_at"],
              "subject": d["subject_id"], "instead_of": d["instead_of_id"], "by": d.get("decided_by"),
              "revs": revs})
        for rank, e in enumerate(d["evidence"]):
            graph.query("""
                MATCH (d:Decision {id:$id}), (c:Chunk {id:$chunk})
                MERGE (d)-[ev:EVIDENCED_BY]->(c)
                SET ev.quote=$quote, ev.source_version=c.source_version, ev.text_hash=c.text_hash, ev.rank=$rank
            """, {"id": d["id"], "chunk": e["chunk_id"], "quote": e["quote"], "rank": rank})
        written.append(d["id"])
    return {"written": written, "rejected": rejected}


def load_snapshots(graph: Graph) -> dict:
    """Load saved extractions for sources that are in the graph (update documents load when they arrive)."""
    present = {r["id"] for r in rows(graph, "MATCH (s:Source) RETURN s.id AS id")}
    out = {}
    for path in sorted((settings.fixture_dir / "extracted").glob("*.json")):
        snap = json.loads(path.read_text())
        if "source_id" not in snap:  # other model snapshots (e.g. skill tags) live here too
            continue
        if snap["source_id"] not in present:
            continue
        if snap["kind"] == "decisions":
            out[snap["source_id"]] = load_decisions(graph, snap)
        elif snap["kind"] == "actions":
            out[snap["source_id"] + " (actions)"] = load_action_items(graph, snap)
    return out


def load_action_items(graph: Graph, snapshot: dict) -> dict:
    """Write verified meeting action items as proposals; a person turns them into tasks."""
    passages = {p["id"]: p for p in source_passages(graph, snapshot["source_id"])}
    written, rejected = [], []
    for a in snapshot["output"].get("actions", []):
        p = passages.get(a.get("chunk_id"))
        owner = rows(graph, "MATCH (x:Person) WHERE toLower(x.name) = toLower($n) RETURN x.id AS id", {"n": a.get("owner", "")})
        problems = []
        if p is None or not _norm(a.get("quote", "")) or _norm(a["quote"]) not in _norm(p["text"]):
            problems.append("quote not found verbatim")
        if len(owner) != 1:
            problems.append(f"owner {a.get('owner')!r} is not exactly one person")
        if problems:
            rejected.append({"item": a, "problems": problems})
            continue
        key = "AI-" + hashlib.sha256(f"{snapshot['source_id']}|{a['owner']}|{a['task']}".encode()).hexdigest()[:8]
        graph.query("""
            MATCH (c:Chunk {id:$chunk}), (o:Person {id:$owner})
            MERGE (ai:ActionItem {id:$id})
            SET ai.task=$task, ai.due=$due, ai.quote=$quote, ai.authority='extracted', ai.extracted_by=$model,
                ai.status=coalesce(ai.status, 'proposed')
            MERGE (ai)-[:FOUND_IN]->(c) MERGE (ai)-[:FOR]->(o)
        """, {"chunk": a["chunk_id"], "owner": owner[0]["id"], "id": key, "task": a["task"], "due": a.get("due"),
              "quote": a["quote"], "model": snapshot["model"]})
        written.append(key)
    return {"written": written, "rejected": rejected}
