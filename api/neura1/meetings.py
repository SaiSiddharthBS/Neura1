"""Meetings: a recording becomes a transcript, verified decisions and action items, linked into the graph.

1. Speech to text runs on Flyvi's own hardware with open-source Whisper (faster-whisper, MIT). The model is primed
   with Flyvi's vocabulary from the graph (people, parts, products, builds, orders, customers), so "Sharath" and
   "BO-0415" come out right. A remote, OpenAI-compatible transcription endpoint (for example on the DGX) can be used
   instead by setting NEURA1_STT_BASE_URL.
2. Identifiers the speech model spells loosely ("BO 0415", "CT 1051") are put back into their graph form by code.
3. The transcript becomes passages of company knowledge with their start and end times, linked to what they mention.
4. The main model (the DGX) reads the passages for decisions and action items. Code keeps only what it can quote word
   for word from the transcript, exactly as for documents and chats.
Nothing leaves the building: the audio, the transcript and the model all run on Flyvi's machines.
"""

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path

from falkordb import Graph

from neura1.config import settings
from neura1.graph import rows
from neura1.ingest.unstructured import entity_lexicon, mentions

AUDIO_TYPES = {".m4a", ".mp3", ".wav", ".aiff", ".aif", ".ogg", ".webm", ".flac", ".mp4", ".mpeg"}
MAX_BYTES = 60 * 1024 * 1024
PASSAGE_SECONDS = 40

_model = None
_model_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

STAGES = ["saved", "transcribing", "linking", "reading", "checking", "done"]


class MeetingError(ValueError):
    pass


def folder() -> Path:
    d = settings.data_dir / "meetings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- speech to text ----------

def vocabulary(graph: Graph) -> str:
    """Names and identifiers the speech model should expect, from the graph."""
    names = [r["v"] for r in rows(graph, """
        MATCH (n) WHERE n:Person OR n:Customer OR n:Supplier RETURN n.name AS v
        UNION MATCH (i:Item) RETURN i.id AS v
        UNION MATCH (b:Build) RETURN b.id AS v
        UNION MATCH (o:Order) RETURN o.id AS v""") if r["v"]]
    words = sorted({n.split(" (")[0] for n in names})
    return "Flyvi Technologies meeting. Names and part numbers: " + ", ".join(words) + "."


def _to_wav(src: Path) -> Path:
    """16 kHz mono WAV, with whatever converter this machine has (ffmpeg, or afconvert on macOS)."""
    out = Path(tempfile.mkstemp(suffix=".wav")[1])
    if shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", "-f", "wav", str(out)]
    elif shutil.which("afconvert"):
        cmd = ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(src), str(out)]
    else:
        raise MeetingError("Install ffmpeg to read audio recordings")
    done = subprocess.run(cmd, capture_output=True, timeout=600)
    if done.returncode != 0:
        raise MeetingError(f"Could not read the recording: {done.stderr.decode(errors='ignore')[:200]}")
    return out


def _samples(wav: Path):
    import numpy as np
    with wave.open(str(wav)) as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise MeetingError("Unexpected audio format after conversion")
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        return data, w.getnframes() / w.getframerate()


def _local_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(settings.stt_model, device="cpu", compute_type="int8")
        return _model


def transcribe(path: Path, prompt: str) -> tuple[list[dict], float, str]:
    """Segments with start and end seconds; the audio length; which engine was used."""
    if settings.stt_base_url:
        from openai import OpenAI
        client = OpenAI(base_url=settings.stt_base_url, api_key=settings.stt_api_key or "none", timeout=600)
        with open(path, "rb") as f:
            r = client.audio.transcriptions.create(model=settings.stt_remote_model, file=f, prompt=prompt,
                                                   response_format="verbose_json")
        segs = [{"start": float(s["start"] if isinstance(s, dict) else s.start),
                 "end": float(s["end"] if isinstance(s, dict) else s.end),
                 "text": (s["text"] if isinstance(s, dict) else s.text).strip()} for s in (r.segments or [])]
        return segs, (segs[-1]["end"] if segs else 0.0), f"{settings.stt_remote_model} (remote)"
    wav = _to_wav(path)
    try:
        audio, seconds = _samples(wav)
    finally:
        wav.unlink(missing_ok=True)
    segments, _ = _local_model().transcribe(audio, beam_size=5, initial_prompt=prompt, vad_filter=False,
                                            condition_on_previous_text=True, word_timestamps=True)
    words = [{"start": w.start, "end": w.end, "word": w.word} for seg in segments for w in (seg.words or [])]
    return words_to_segments(words), seconds, f"Whisper {settings.stt_model} on this machine"


SPEAKER = re.compile(r"^[A-Z][a-z]+$")


def words_to_segments(words: list[dict], longest: float = 30.0) -> list[dict]:
    """Group timed words into readable segments: a new one starts where a speaker introduces themselves ("Ambika
    here") and at sentence ends once a segment is long enough, so every line has an exact start time."""
    out, cur = [], []

    def flush():
        if cur:
            text = "".join(w["word"] for w in cur).strip()
            if text:
                out.append({"start": round(cur[0]["start"], 2), "end": round(cur[-1]["end"], 2), "text": text})
            cur.clear()

    for i, w in enumerate(words):
        token = w["word"].strip().strip(",.")
        nxt = words[i + 1]["word"].strip().strip(",.").lower() if i + 1 < len(words) else ""
        if cur and SPEAKER.match(token) and nxt == "here":
            flush()
        cur.append(w)
        ends_sentence = w["word"].rstrip().endswith((".", "?", "!"))
        if ends_sentence and cur[-1]["end"] - cur[0]["start"] >= longest:
            flush()
    flush()
    return out


def fix_orgs(text: str, orgs: list[str]) -> str:
    """Supplier and customer names anchored on their distinctive last word: "Dakton Components" -> "Deccan
    Components" (only when the first word is still a plausible match)."""
    import difflib
    for org in orgs:
        words = org.split(" (")[0].split()
        if len(words) < 2:
            continue
        first, rest = words[0], " ".join(words[1:])

        def swap(m, first=first, rest=rest):
            close = difflib.SequenceMatcher(None, m.group(1).lower(), first.lower()).ratio() >= 0.45
            return f"{first} {rest}" if close else m.group(0)

        text = re.sub(r"\b([A-Za-z]+) " + re.escape(rest) + r"\b", swap, text, flags=re.I)
    return text


def fix_names(text: str, names: list[str]) -> str:
    """Snap near-misses of known names to the name ("Hitesh here" -> "Hithesh here"), only where a speaker is named
    or the match is very close, so ordinary words are never changed."""
    import difflib
    known = sorted({n for n in names if n and len(n) >= 4})

    def speaker(m):
        best = difflib.get_close_matches(m.group(1), known, n=1, cutoff=0.75)
        return f"{best[0] if best else m.group(1)} here"

    text = re.sub(r"\b([A-Z][a-z]+) here\b", speaker, text)

    def word(m):
        w = m.group(0)
        if w in known or len(w) < 5:
            return w
        best = difflib.get_close_matches(w, known, n=1, cutoff=0.88)
        return best[0] if best else w

    return re.sub(r"\b[A-Z][a-z]{4,}\b", word, text)


def canonical(text: str, ids: list[str]) -> str:
    """Put identifiers back in their graph form: "BO 0415" -> "BO-0415", "ct 1051" -> "CT-1051"."""
    for ident in sorted(ids, key=len, reverse=True):
        letters_digits = re.findall(r"[A-Za-z]+|\d+", ident)
        if len(letters_digits) < 2:
            continue
        pattern = r"[\s\-.]*".join(re.escape(x) for x in letters_digits)
        # A number run into an identifier ("60CT-1051") gets its space back.
        text = re.sub(r"(?<=\d)(?=" + pattern + r"\b)", " ", text, flags=re.I)
        text = re.sub(r"(?<![A-Za-z0-9])" + pattern + r"(?![A-Za-z0-9])", ident, text, flags=re.I)
    return text


# ---------- the pipeline ----------

def status(meeting_id: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(meeting_id)
        return dict(job) if job else None


def _set(meeting_id: str, **kw) -> None:
    with _jobs_lock:
        _jobs.setdefault(meeting_id, {}).update(kw)


def start(graph: Graph, filename: str, data: bytes, title: str | None, by: str) -> str:
    """Save the recording and process it in the background. Returns the meeting id."""
    ext = Path(filename or "").suffix.lower()
    if ext not in AUDIO_TYPES:
        raise MeetingError(f"Unsupported audio type {ext or '(none)'}: use m4a, mp3, wav, aiff, ogg, webm or flac")
    if not data or len(data) > MAX_BYTES:
        raise MeetingError("The recording is empty or larger than 60 MB")
    meeting_id = f"MTG-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:6]}"
    path = folder() / f"{meeting_id}{ext}"
    path.write_bytes(data)
    name = (title or Path(filename).stem.replace("_", " ")).strip()[:120] or "Meeting"
    _set(meeting_id, id=meeting_id, title=name, stage="saved", error=None, started_at=_now(), by=by, audio=path.name)
    threading.Thread(target=_run, args=(graph, meeting_id, path, name, by), daemon=True,
                     name=f"neura1-meeting-{meeting_id}").start()
    return meeting_id


def _run(graph: Graph, meeting_id: str, path: Path, title: str, by: str) -> None:
    from neura1 import llm
    from neura1.ingest import extract
    try:
        _set(meeting_id, stage="transcribing")
        segs, seconds, engine = transcribe(path, vocabulary(graph))
        if not segs:
            raise MeetingError("No speech was found in the recording")
        _set(meeting_id, stage="linking", engine=engine, seconds=round(seconds, 1))
        ids = [r["id"] for r in rows(graph, "MATCH (n) WHERE n:Item OR n:Build OR n:Order OR n:Revision "
                                             "RETURN n.id AS id")]
        names = [r["n"] for r in rows(graph, "MATCH (p:Person) RETURN p.name AS n")]
        orgs = [r["n"] for r in rows(graph, "MATCH (n) WHERE n:Supplier OR n:Customer RETURN n.name AS n") if r["n"]]
        for s in segs:
            s["text"] = fix_orgs(fix_names(canonical(s["text"], ids), names), orgs)
        source_id = f"meetings/{meeting_id}"
        _store(graph, source_id, meeting_id, title, segs, seconds, engine, path.name, by)
        result = {"decisions": [], "actions": [], "rejected": 0}
        if llm.status().get("on_fallback"):
            _set(meeting_id, note="The main model is not reachable: the transcript is saved; decisions will be read "
                                  "when it is back.")
        else:
            _set(meeting_id, stage="reading")
            passages = extract.source_passages(graph, source_id)
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as pool:  # both readings at once on the DGX
                dec_f = pool.submit(extract.run_model, graph, source_id, "decisions", passages)
                act_f = pool.submit(extract.run_model, graph, source_id, "actions", passages)
                dec, act = dec_f.result(), act_f.result()
            _set(meeting_id, stage="checking")
            d = extract.load_decisions(graph, dec)
            a = extract.load_action_items(graph, act)
            result = {"decisions": d["written"], "actions": a["written"],
                      "rejected": len(d["rejected"]) + len(a["rejected"]), "model": dec.get("model")}
            graph.query("MATCH (s:Source {id:$id}) SET s.extracted_version = s.version, s.extracted_at = $at",
                        {"id": source_id, "at": _now()})
        _set(meeting_id, stage="done", result=result, finished_at=_now())
        _announce(graph, meeting_id, title, result)
    except Exception as exc:  # reported on the meeting page
        _set(meeting_id, stage="failed", error=str(exc)[:400])


def _store(graph: Graph, source_id: str, meeting_id: str, title: str, segs: list[dict], seconds: float,
           engine: str, audio: str, by: str) -> None:
    """Passages of about 40 seconds, each linked to what it mentions, with its start and end time."""
    lex = entity_lexicon(graph)
    people = {r["id"]: r["name"] for r in rows(graph, "MATCH (p:Person) RETURN p.id AS id, p.name AS name")}
    # One passage per speaker turn: a turn starts where someone says "<name> here". Long turns are split.
    passages, cur = [], []
    for s in segs:
        starts_turn = re.match(r"^[A-Z][a-z]+ here\b", s["text"])
        if cur and (starts_turn or s["end"] - cur[0]["start"] > PASSAGE_SECONDS):
            passages.append(cur)
            cur = []
        cur.append(s)
    if cur:
        passages.append(cur)
    now = _now()
    version = hashlib.sha256(json.dumps(segs).encode()).hexdigest()[:12]
    graph.query("""
        MERGE (s:Source {id:$id})
        SET s.kind='meeting', s.title=$title, s.uri=$id, s.authority='source_document', s.version=$v,
            s.audio=$audio, s.seconds=$sec, s.engine=$engine, s.recorded_by=$by, s.first_seen=coalesce(s.first_seen, $now),
            s.updated_at=$now, s.segments=$segs
    """, {"id": source_id, "title": title, "v": version, "audio": audio, "sec": round(seconds, 1), "engine": engine,
          "by": by, "now": now, "segs": json.dumps(segs)})
    for n, group in enumerate(passages):
        text = " ".join(s["text"] for s in group)
        cid = f"{source_id}#p{n}"
        graph.query("""
            MATCH (s:Source {id:$sid})
            MERGE (c:Chunk {id:$cid})
            SET c.text=$text, c.ordinal=$n, c.ts=$now, c.start=$start, c.end=$end, c.kind='meeting',
                c.source_version=$v, c.text_hash=$hash
            MERGE (c)-[:PART_OF]->(s)
        """, {"sid": source_id, "cid": cid, "text": text, "n": n, "now": now, "start": group[0]["start"],
              "end": group[-1]["end"], "v": version, "hash": hashlib.sha256(text.encode()).hexdigest()[:12]})
        targets = sorted(mentions(text, lex) - {source_id})
        if targets:
            graph.query("MATCH (c:Chunk {id:$cid}) UNWIND $t AS tid MATCH (x {id:tid}) MERGE (c)-[:MENTIONS]->(x)",
                        {"cid": cid, "t": targets})
        speaker = re.match(r"^([A-Z][a-z]+) here\b", text)
        pid = next((k for k, v in people.items() if speaker and v == speaker.group(1)), None)
        if pid:  # speakers introduce themselves: "Ambika here."
            graph.query("""MATCH (c:Chunk {id:$cid}), (p:Person {id:$p})
                           SET c.author = p.name, c.author_id = p.id MERGE (c)-[:SAID_BY]->(p)""",
                        {"cid": cid, "p": pid})


def _announce(graph: Graph, meeting_id: str, title: str, result: dict) -> None:
    from neura1 import chat
    n_d, n_a = len(result["decisions"]), len(result["actions"])
    if not (n_d or n_a):
        return
    chat.notify(graph, "evidence", f"Neura1 listened to “{title}”: {n_d} decision{'s' if n_d != 1 else ''} and {n_a} "
                                   f"action item{'s' if n_a != 1 else ''}, each checked word for word against the "
                                   f"transcript.", [{"label": "Open the meeting", "href": f"/meetings?id={meeting_id}"}])


# ---------- reading back ----------

def get(graph: Graph, meeting_id: str) -> dict | None:
    source_id = f"meetings/{meeting_id}"
    src = rows(graph, """MATCH (s:Source {id:$id}) RETURN s.title AS title, s.audio AS audio, s.seconds AS seconds,
                         s.engine AS engine, s.segments AS segments, s.first_seen AS at, s.recorded_by AS by""",
               {"id": source_id})
    job = status(meeting_id)
    if not src:
        return job | {"status": "processing"} if job else None
    s = src[0]
    passages = rows(graph, """MATCH (c:Chunk)-[:PART_OF]->(:Source {id:$id})
                              OPTIONAL MATCH (c)-[:MENTIONS]->(x) WHERE NOT x:Source
                              RETURN c.id AS id, c.text AS text, c.start AS start, c.end AS end, c.ordinal AS n,
                                     collect(DISTINCT {id: x.id, label: labels(x)[0], name: coalesce(x.name, x.id)}) AS about
                              ORDER BY n""", {"id": source_id})
    when = {p["id"]: p["start"] for p in passages}
    found = rows(graph, """
        MATCH (d:Decision)-[e:EVIDENCED_BY]->(c:Chunk)-[:PART_OF]->(:Source {id:$id})
        OPTIONAL MATCH (d)-[:ABOUT]->(i:Item)
        OPTIONAL MATCH (d)-[:INSTEAD_OF]->(inc:Item)
        RETURN d.id AS id, d.outcome AS outcome, d.summary AS summary, d.reason AS reason, i.id AS subject,
               inc.id AS instead_of, c.id AS chunk, e.quote AS quote""", {"id": source_id})
    decisions: dict[str, dict] = {}
    for d in found:  # one decision, with every moment of the recording that supports it
        x = decisions.setdefault(d["id"], {k: d[k] for k in ("id", "outcome", "summary", "reason", "subject",
                                                             "instead_of")} | {"evidence": []})
        x["evidence"].append({"chunk": d["chunk"], "quote": d["quote"], "at": when.get(d["chunk"])})
    for x in decisions.values():
        x["evidence"].sort(key=lambda e: e["at"] if e["at"] is not None else 0)
        x["at"] = x["evidence"][-1]["at"]  # the moment it was decided is usually the last one
    decisions = sorted(decisions.values(), key=lambda x: x["at"] or 0)
    actions = rows(graph, """
        MATCH (ai:ActionItem)-[:FOUND_IN]->(c:Chunk)-[:PART_OF]->(:Source {id:$id})
        OPTIONAL MATCH (ai)-[:FOR]->(p:Person)
        RETURN ai.id AS id, ai.task AS task, ai.due AS due, ai.quote AS quote, ai.status AS status, p.id AS owner_id,
               p.name AS owner, c.id AS chunk""", {"id": source_id})
    for a in actions:
        a["at"] = when.get(a["chunk"])
    return {"id": meeting_id, "status": "ready", "title": s["title"], "audio": s["audio"], "seconds": s["seconds"],
            "engine": s["engine"], "recorded_at": s["at"], "by": s["by"],
            "segments": json.loads(s["segments"] or "[]"), "passages": passages, "decisions": decisions,
            "actions": actions, "job": job}


def list_meetings(graph: Graph) -> list[dict]:
    done = rows(graph, """MATCH (s:Source {kind:'meeting'})
                          OPTIONAL MATCH (d:Decision)-[:EVIDENCED_BY]->(:Chunk)-[:PART_OF]->(s)
                          OPTIONAL MATCH (ai:ActionItem)-[:FOUND_IN]->(:Chunk)-[:PART_OF]->(s)
                          RETURN s.id AS source, s.title AS title, s.seconds AS seconds, s.first_seen AS at,
                                 count(DISTINCT d) AS decisions, count(DISTINCT ai) AS actions ORDER BY at DESC""")
    out = [{"id": d["source"].split("/", 1)[1], "status": "ready"} | {k: d[k] for k in ("title", "seconds", "at",
                                                                                          "decisions", "actions")}
           for d in done]
    known = {o["id"] for o in out}
    with _jobs_lock:
        for j in _jobs.values():
            # Recordings still being processed, or that failed. A finished job without its meeting in the graph
            # (for example after a reset) is not shown.
            if j["id"] not in known and j.get("stage") != "done":
                out.insert(0, {"id": j["id"], "status": j["stage"], "title": j["title"], "at": j["started_at"],
                               "seconds": j.get("seconds"), "decisions": 0, "actions": 0, "error": j.get("error")})
    return out


def forget_jobs() -> None:
    """After a reset: the graph no longer holds these meetings."""
    with _jobs_lock:
        _jobs.clear()


def audio_path(meeting_id: str) -> Path | None:
    if not re.fullmatch(r"MTG-\d{8}-[0-9a-f]{6}", meeting_id):
        return None
    hits = [p for p in folder().glob(f"{meeting_id}.*") if p.suffix.lower() in AUDIO_TYPES]
    return hits[0] if hits else None
