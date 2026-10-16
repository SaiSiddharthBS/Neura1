"use client";

import { ClipboardCheck, FileText, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, type TraceStep } from "@/lib/api";

type Draft = { owner: string; title: string; target: string | null; why: string };
type Answer = { answer: string; warnings?: string[]; sources?: string[]; drafts?: Draft[]; tool_calls: { tool: string; args: Record<string, unknown> }[]; trace: TraceStep[] };

const EXAMPLES = [
  "Can we switch from NB54360 to NB54361-L?",
  "Who should a new firmware engineer talk to about pmic_seq.c?",
  "What is the status of the VC-300 project and who is on it?",
  "What happened with the Kaveri brownouts?",
  "Ask Rahul to review pmic_seq.c for MX-3360",
];

export default function AskBox({ onOpen, initial }: { onOpen?: (chunk: string) => void; initial?: string }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [a, setA] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);

  const started = useRef(false);
  useEffect(() => {
    if (initial && !started.current) { started.current = true; ask(initial); }
  }, [initial]);

  async function ask(question: string) {
    setQ(question);
    setBusy(true);
    setError(null);
    setA(null);
    try {
      setA(await api<Answer>("/api/ask", { method: "POST", body: JSON.stringify({ question }) }));
    } catch (e) {
      setError(e instanceof ApiError && e.status === 503
        ? "The model is not connected right now. Everything else in Neura1 (impact, costs, evidence) works without it."
        : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card p-4">
      <div className="flex items-center gap-2 font-medium"><Sparkles size={16} className="text-accent" /> Ask the company brain</div>
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) ask(q.trim()); }} className="mt-3 flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask anything about Voltline's products, parts, people and decisions"
               className="flex-1 rounded-md border border-line px-3 py-2 text-sm" />
        <button disabled={busy} className="rounded-md bg-accent px-4 text-sm text-white disabled:opacity-50">{busy ? "Thinking…" : "Ask"}</button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((x) => (
          <button key={x} onClick={() => ask(x)} className="rounded-full border border-line px-2.5 py-0.5 text-xs text-muted hover:border-ink hover:text-ink">{x}</button>
        ))}
      </div>
      {busy && <p className="mt-3 text-sm text-muted">Looking things up in the graph. On a laptop CPU a local model can take a few minutes; on a GPU it takes seconds.</p>}
      {error && <p className="mt-3 text-sm text-warn">{error}</p>}
      {a && (
        <div className="mt-4 space-y-3">
          {a.warnings?.map((w) => (
            <div key={w} className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{w}</div>
          ))}
          <div className="whitespace-pre-wrap rounded-lg bg-bg p-3 text-sm leading-relaxed">{a.answer}</div>
          {a.sources && a.sources.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-muted">Sources:</span>
              {a.sources.map((s) => (
                <button key={s} onClick={() => onOpen?.(s)} className="flex items-center gap-1 rounded-md border border-line px-2 py-0.5 hover:border-ink">
                  <FileText size={11} /> {s.split("/").pop()}
                </button>
              ))}
            </div>
          )}
          {a.drafts?.map((d, i) => <DraftTask key={i} d={d} />)}
          <details className="text-sm">
            <summary className="cursor-pointer text-muted">
              How this was answered: {a.tool_calls.length} tool calls, {a.trace.length} Cypher queries
            </summary>
            <ol className="mt-2 space-y-2">
              {a.tool_calls.map((t, i) => (
                <li key={i} className="font-mono text-xs">{i + 1}. {t.tool}({JSON.stringify(t.args)})</li>
              ))}
            </ol>
            {a.trace.map((t, i) => (
              <pre key={i} className="mt-2 overflow-x-auto rounded-md border border-line bg-bg p-2 text-[11px]">
                {`// ${t.name} · ${t.rows} rows · ${t.ms} ms\n${t.cypher}`}
              </pre>
            ))}
          </details>
        </div>
      )}
    </section>
  );
}

function DraftTask({ d }: { d: Draft }) {
  const [state, setState] = useState<string | null>(null);
  async function create() {
    let pass = "", name = "";
    try { pass = localStorage.getItem("neura1-passcode") ?? ""; name = localStorage.getItem("neura1-reviewer") ?? ""; } catch {}
    pass = pass || prompt("Demo passcode") || "";
    name = name || prompt("Your name") || "";
    if (!pass || !name) return;
    try { localStorage.setItem("neura1-passcode", pass); localStorage.setItem("neura1-reviewer", name); } catch {}
    try {
      const r = await api<{ id: string; new: boolean; owner: string | null }>("/api/tasks", {
        method: "POST", write: true, body: JSON.stringify({ ...d, created_by: name }),
      });
      setState(r.new ? `Created ${r.id} for ${r.owner ?? "nobody (owner not found)"}` : `Already exists (${r.id})`);
    } catch (e) {
      setState((e as Error).message);
    }
  }
  return (
    <div className="rounded-lg border border-accent/40 bg-accent/12 p-3 text-sm">
      <div className="flex items-center gap-2 font-medium text-accent"><ClipboardCheck size={15} /> Draft task, not created yet</div>
      <div className="mt-1"><b>{d.title}</b> → {d.owner}{d.target ? ` · ${d.target}` : ""}</div>
      {d.why && <div className="text-xs text-muted">{d.why}</div>}
      {state ? <div className="mt-2 text-xs">{state}</div> :
        <button onClick={create} className="mt-2 rounded-md bg-accent px-3 py-1 text-xs text-white">Create task</button>}
    </div>
  );
}
