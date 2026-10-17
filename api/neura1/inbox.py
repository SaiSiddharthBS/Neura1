"""Signals arrive on their own: drop or forward an email, a PDF or a text note, and Neura1 takes it from there.

A folder (data/mail-drop/) works like a shared inbox. Any .eml (a forwarded email), .pdf, .md or .txt placed there is
read, classified as a supplier notice, a customer escalation or a leave notice, stored as a source, read by the model
(notices), linked to the parts, customers and people it names, and announced in the right chat channel. Processed
files move to mail-drop/processed/, so nothing is read twice.
"""

import email
import re
import threading
import time
from datetime import datetime
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path

from falkordb import Graph

from neura1.config import settings

DROP = "mail-drop"
KINDS = ("notice", "escalation", "leave")
ESCALATION = re.compile(r"\b(escalat\w*|complain\w*|unhappy|hold (the )?acceptance|penalt\w*|urgent|failure|field issue)\b", re.I)
LEAVE = re.compile(r"\b(leave|vacation|time off|away from|out of office|sick)\b", re.I)
NOTICE = re.compile(r"\b(price|lead[- ]time|end[- ]of[- ]life|EOL|last[- ]time[- ]buy|PCN|discontinu\w*|allocation)\b", re.I)


def drop_dir() -> Path:
    d = settings.data_dir / DROP
    (d / "processed").mkdir(parents=True, exist_ok=True)
    return d


def parse_email(raw: bytes) -> dict:
    """Subject, sender, date, plain-text body and attachments of a forwarded email (.eml)."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body else ""
    if body is not None and body.get_content_type() == "text/html":
        text = re.sub(r"<[^>]+>", " ", text)
    attachments = [(a.get_filename() or "attachment", a.get_payload(decode=True) or b"")
                   for a in msg.iter_attachments()]
    when = None
    try:
        when = parsedate_to_datetime(msg["Date"]).date().isoformat() if msg["Date"] else None
    except (TypeError, ValueError):
        pass
    return {"subject": str(msg["Subject"] or "Forwarded email"), "sender": str(msg["From"] or ""), "date": when,
            "body": text.strip(), "attachments": attachments}


def classify(subject: str, body: str) -> str:
    """Which kind of signal this is. A supplier's price or lead-time change wins over everything else."""
    head = f"{subject}\n{body[:1500]}"
    if NOTICE.search(head):
        return "notice"
    if LEAVE.search(subject) or (LEAVE.search(head) and not ESCALATION.search(head)):
        return "leave"
    if ESCALATION.search(head):
        return "escalation"
    return "notice"


def ingest(graph: Graph, path: Path, kind: str) -> dict:
    """Store one signal file (already in data/uploads/inbox/) and act on it. Shared by uploads and the mail drop."""
    from neura1 import chat
    from neura1.ingest import extract
    from neura1.ingest.unstructured import load_sources
    from neura1.llm import LLMUnavailable

    load_sources(graph, root=settings.data_dir, files=[path])
    source_id = str(path.relative_to(settings.data_dir))
    model_error, snap = None, None
    if kind == "notice":
        try:
            snap = extract.with_resolved_part(graph, extract.run_model(graph, source_id, "notice"))
            text = "\n".join(p["text"] for p in extract.source_passages(graph, source_id))
            snap = snap | {"problems": extract.verify_notice(snap["output"], text)}
        except LLMUnavailable as exc:
            model_error = str(exc)
        except Exception as exc:  # a model failure must not lose the notice; a person can enter the facts
            model_error = f"Model could not read the notice: {exc}"
        checked = bool(snap) and not snap.get("problems")
        part = (snap or {}).get("output", {}).get("part") if checked else None
        chat.notify(graph, "supplier_change", f"A supplier notice arrived{f' about {part}' if part else ''}. "
                    + ("Its facts were read and checked." if checked else "Its facts still need entering."),
                    [{"label": "Signals", "href": "/signals"}])
    elif kind == "escalation":
        chat.notify(graph, "escalation", "A customer escalation arrived. Neura1 linked it to the customer, orders and "
                    "tickets it names; the escalation plan is on the customer's page.", [{"label": "Signals", "href": "/signals"}])
    else:
        chat.notify(graph, "absence", "A leave notice arrived. The handover plan is ready for the person's manager.",
                    [{"label": "Signals", "href": "/signals"}])
    return {"source_id": source_id, "kind": kind, "extraction": snap, "model_error": model_error}


def _stage(kind: str, suffix: str, data: bytes | str) -> Path:
    inbox = settings.data_dir / "uploads" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = inbox / f"{kind}-{stamp}{suffix}"
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")
    return path


_lock = threading.Lock()


def process_drop(graph: Graph) -> list[dict]:
    """Handle every file waiting in the mail drop, oldest first."""
    with _lock:
        folder = drop_dir()
        files = sorted((p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")), key=lambda p: p.stat().st_mtime)
        return [d for f in files for d in process_file(graph, f)]


def process_file(graph: Graph, f: Path) -> list[dict]:
    """Read one email or notice file, act on it, and move it to mail-drop/processed/."""
    done: list[dict] = []
    folder = drop_dir()
    try:
        if f.suffix.lower() == ".eml":
            m = parse_email(f.read_bytes())
            kind = classify(m["subject"], m["body"])
            text = (f"# {m['subject']}\n\nFrom: {m['sender']}\n"
                    + (f"Date: {m['date']}\n" if m["date"] else "") + f"\n{m['body']}\n")
            done.append(ingest(graph, _stage(kind, ".md", text), kind) | {"file": f.name})
            for name, blob in m["attachments"]:  # a PDF notice attached to the email is read too
                if name.lower().endswith(".pdf") and blob:
                    done.append(ingest(graph, _stage(kind, ".pdf", blob), kind) | {"file": f"{f.name} / {name}"})
        elif f.suffix.lower() in (".md", ".txt"):
            text = f.read_text(errors="replace")
            kind = classify(f.stem.replace("_", " "), text)
            if not text.lstrip().startswith("#"):
                text = f"# {f.stem.replace('_', ' ')}\n\n{text}"
            done.append(ingest(graph, _stage(kind, ".md", text), kind) | {"file": f.name})
        elif f.suffix.lower() == ".pdf":
            kind = classify(f.stem.replace("_", " "), "")
            done.append(ingest(graph, _stage(kind, ".pdf", f.read_bytes()), kind) | {"file": f.name})
        else:
            return done
    except Exception as exc:  # one bad file must not stop the inbox
        done.append({"file": f.name, "error": str(exc)})
    f.rename(folder / "processed" / f"{datetime.now():%Y%m%d-%H%M%S}-{f.name}")
    return done


_watcher_started = False


def start_watcher(get_graph, every: float = 5.0) -> None:
    """Check the mail drop every few seconds in the background."""
    global _watcher_started
    if _watcher_started:
        return
    _watcher_started = True

    def loop():
        while True:
            try:
                if any(p.is_file() and not p.name.startswith(".") for p in drop_dir().iterdir()):
                    process_drop(get_graph())
            except Exception:
                pass  # the graph may be restarting; try again next time
            time.sleep(every)

    threading.Thread(target=loop, daemon=True, name="neura1-mail-drop").start()
