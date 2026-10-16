"use client";

import { FileText, History, Loader2, MessageSquarePlus, Sparkles, Wrench } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import DraftTask from "@/components/DraftTask";
import { viewerId, api, type TraceStep } from "@/lib/api";

type Draft = { owner: string; title: string; target: string | null; why: string };
type Step = { tool: string; args: Record<string, unknown> };
type Turn = {
  question: string; answer?: string; warnings?: string[]; sources?: string[]; drafts?: Draft[];
  steps: Step[]; trace?: TraceStep[]; error?: string; pending?: boolean;
};
type Conv = { id: string; title: string; started_at: string; turns: number };

const EXAMPLES = [
  "Can we switch from NB54360 to NB54361-L?",
  "Who knows CAN bus, and what are they working on?",
  "What happens if Raghavendra is away in November?",
  "What is Konkan Naval unhappy about?",
  "Ask Sai to review pmic_seq.c for MX-3360",
];

export default function AskBox({ onOpen, initial }: { onOpen?: (chunk: string) => void; initial?: string }) {
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [cid, setCid] = useState<string | null>(null);
  const [convs, setConvs] = useState<Conv[]>([]);
  const [busy, setBusy] = useState(false);
  const started = useRef(false);

  const loadConvs = useCallback(() => api<Conv[]>("/api/conversations").then(setConvs).catch(() => {}), []);
  useEffect(() => { api<Conv[]>("/api/conversations").then(setConvs).catch(() => {}); }, []);

  const ask = useCallback(async (question: string) => {
    setBusy(true);
    setQ("");
    setTurns((t) => [...t, { question, steps: [], pending: true }]);
    const update = (fn: (t: Turn) => Turn) => setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? fn(t) : t)));
    try {
      const res = await fetch("/api/ask/stream", {
        method: "POST", headers: { "content-type": "application/json", "x-neura1-as": viewerId() },
        body: JSON.stringify({ question, conversation_id: cid }),
      });
      if (res.status === 503) throw new Error("The model is not connected right now. Everything else in Neura1 works without it.");
      const reader = res.body!.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const ev = JSON.parse(line.slice(6));
          if (ev.type === "tool") update((t) => ({ ...t, steps: [...t.steps, { tool: ev.tool, args: ev.args }] }));
          if (ev.type === "error") update((t) => ({ ...t, pending: false, error: ev.detail }));
          if (ev.type === "answer") {
            setCid(ev.conversation_id);
            update((t) => ({ ...t, pending: false, answer: ev.answer, warnings: ev.warnings, sources: ev.sources, drafts: ev.drafts, trace: ev.trace }));
          }
        }
      }
    } catch (e) {
      update((t) => ({ ...t, pending: false, error: (e as Error).message }));
    } finally {
      setBusy(false);
      loadConvs();
    }
  }, [cid, loadConvs]);

  useEffect(() => {
    if (initial && !started.current) { started.current = true; setTimeout(() => ask(initial), 0); }
  }, [initial, ask]);

  async function openConv(id: string) {
    const t = await api<{ question: string; answer: string; sources: string[] }[]>(`/api/conversations/${id}`);
    setCid(id);
    setTurns(t.map((x) => ({ question: x.question, answer: x.answer, sources: x.sources, steps: [] })));
  }

  return (
    <section className="card grid gap-0 lg:grid-cols-[220px_1fr]">
      <aside className="border-b border-line p-3 lg:border-b-0 lg:border-r">
        <button onClick={() => { setCid(null); setTurns([]); }} className="flex w-full items-center gap-2 rounded-lg bg-accent/15 px-3 py-2 text-sm text-accent-hover hover:bg-accent/25">
          <MessageSquarePlus size={14} /> New conversation
        </button>
        <div className="mt-3 flex items-center gap-1.5 px-1 text-[10.5px] uppercase tracking-[0.12em] text-muted"><History size={11} /> Remembered</div>
        <div className="mt-1 max-h-72 space-y-0.5 overflow-y-auto">
          {convs.map((c) => (
            <button key={c.id} onClick={() => openConv(c.id)} className={`block w-full truncate rounded-md px-2 py-1.5 text-left text-xs hover:bg-elev ${c.id === cid ? "bg-elev text-ink" : "text-muted"}`}>
              {c.title}<span className="block text-[10px] text-muted">{c.turns} turns · {c.started_at.slice(0, 10)}</span>
            </button>
          ))}
          {!convs.length && <div className="px-2 text-xs text-muted">Conversations you start are stored in the graph.</div>}
        </div>
      </aside>
      <div className="flex min-h-[420px] flex-col p-4">
        <div className="flex items-center gap-2 font-medium"><Sparkles size={16} className="text-cyan" /> Ask the company brain</div>
        <div className="mt-3 flex-1 space-y-4">
          {!turns.length && (
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLES.map((x) => <button key={x} onClick={() => ask(x)} className="rounded-full border border-line px-2.5 py-1 text-xs text-muted hover:border-line2 hover:text-ink">{x}</button>)}
            </div>
          )}
          {turns.map((t, i) => (
            <div key={i} className="space-y-2">
              <div className="ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-sm bg-accent/20 px-3 py-2 text-sm">{t.question}</div>
              {(t.steps.length > 0 || t.pending) && (
                <div className="space-y-1 text-xs text-muted">
                  {t.steps.map((s, k) => (
                    <div key={k} className="flex items-center gap-1.5 font-mono"><Wrench size={11} className="text-accent-hover" />{s.tool}({Object.values(s.args).map((v) => JSON.stringify(v)).join(", ")})</div>
                  ))}
                  {t.pending && <div className="flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> Working through the graph. On a laptop CPU each step takes a while; on a GPU, seconds.</div>}
                </div>
              )}
              {t.error && <div className="rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm text-warn">{t.error}</div>}
              {t.warnings?.map((w) => <div key={w} className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{w}</div>)}
              {t.answer && <div className="w-fit max-w-[90%] whitespace-pre-wrap rounded-2xl rounded-bl-sm bg-elev px-3 py-2 text-sm leading-relaxed">{t.answer}</div>}
              {t.sources && t.sources.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="text-muted">Sources:</span>
                  {t.sources.map((s) => (
                    <button key={s} onClick={() => onOpen?.(s)} className="flex items-center gap-1 rounded-md border border-line px-2 py-0.5 hover:border-line2"><FileText size={11} /> {s.split("/").pop()}</button>
                  ))}
                </div>
              )}
              {t.drafts?.map((d, k) => <DraftTask key={k} d={d} />)}
              {t.trace && t.trace.length > 0 && (
                <details className="text-xs text-muted"><summary className="cursor-pointer">{t.trace.length} Cypher queries</summary>
                  {t.trace.map((x, k) => <pre key={k} className="mt-1 overflow-x-auto rounded-md border border-line bg-elev p-2 text-[11px]">{`// ${x.name} · ${x.rows} rows · ${x.ms} ms\n${x.cypher}`}</pre>)}
                </details>
              )}
            </div>
          ))}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); if (q.trim() && !busy) ask(q.trim()); }} className="mt-4 flex gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={turns.length ? "Ask a follow-up…" : "Ask anything about Flyvi's people, projects, products, customers and decisions"}
                 className="flex-1 rounded-xl border border-line px-3 py-2.5 text-sm" />
          <button disabled={busy} className="rounded-xl bg-accent px-4 text-sm text-white hover:bg-accent-hover disabled:opacity-50">{busy ? "Thinking…" : "Ask"}</button>
        </form>
      </div>
    </section>
  );
}
