"use client";

import { ArrowUp, FileText, History, Loader2, MessageSquarePlus, Sparkles, Wrench } from "lucide-react";
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
  "What is slipping against the plan, and why?",
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

  const thinking = turns.some((t) => t.pending);
  return (
    <section data-tour="ask" className="card grid min-h-[560px] overflow-hidden lg:grid-cols-[232px_1fr]">
      <aside className="border-b border-line bg-bg-raised/40 p-3 lg:border-b-0 lg:border-r">
        <button onClick={() => { setCid(null); setTurns([]); }}
                className="flex w-full items-center gap-2 rounded-lg border border-line bg-panel px-3 py-2 text-[13px] font-medium shadow-[var(--shadow)] transition hover:border-line2">
          <MessageSquarePlus size={14} className="text-accent" /> New conversation
        </button>
        <div className="mt-4 flex items-center gap-1.5 px-1 text-[11px] font-medium text-faint"><History size={11} /> Remembered in the graph</div>
        <div className="mt-1.5 max-h-[440px] space-y-px overflow-y-auto">
          {convs.map((c) => (
            <button key={c.id} onClick={() => openConv(c.id)}
                    className={`block w-full rounded-lg px-2.5 py-2 text-left transition ${c.id === cid ? "bg-elev-strong" : "hover:bg-elev"}`}>
              <span className="block truncate text-[13px]">{c.title}</span>
              <span className="block text-[11px] text-faint">{c.turns} turn{c.turns === 1 ? "" : "s"} · {c.started_at.slice(0, 10)}</span>
            </button>
          ))}
          {!convs.length && <div className="px-2.5 py-2 text-[12px] text-muted">Your conversations are stored as Conversation and Turn nodes, so follow-ups keep their context.</div>}
        </div>
      </aside>

      <div className="flex min-h-0 flex-col">
        <div className="flex-1 space-y-7 overflow-y-auto px-5 py-6 lg:px-8">
          {!turns.length && (
            <div className="mx-auto flex max-w-2xl flex-col items-center pt-6 text-center">
              <span className="ai-ring grid h-12 w-12 place-items-center rounded-2xl bg-panel"><Sparkles size={22} className="text-accent" /></span>
              <h2 className="mt-4 text-[22px] font-semibold tracking-tight">What do you want to know?</h2>
              <p className="mt-1 text-[14px] text-muted">Neura1 plans its own graph queries, shows every step, and cites the messages and documents behind each answer.</p>
              <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
                {EXAMPLES.map((x) => (
                  <button key={x} onClick={() => ask(x)}
                          className="rounded-xl border border-line bg-panel px-3.5 py-3 text-left text-[13px] text-ink-soft shadow-[var(--shadow)] transition hover:border-line2 hover:text-ink">{x}</button>
                ))}
              </div>
            </div>
          )}
          {turns.map((t, i) => (
            <div key={i} className="space-y-3">
              <div className="ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-md bg-elev-strong px-4 py-2.5 text-[14px]">{t.question}</div>
              <div className="flex gap-3">
                <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-accent to-violet text-white ${t.pending ? "animate-pulse" : ""}`}><Sparkles size={14} /></span>
                <div className="min-w-0 flex-1 space-y-3">
                  {(t.steps.length > 0 || t.pending) && (
                    <details open={t.pending} className="group rounded-xl border border-line bg-bg-raised/50 px-3 py-2">
                      <summary className="flex cursor-pointer list-none items-center gap-2 text-[12.5px] text-muted">
                        {t.pending ? <Loader2 size={13} className="animate-spin text-accent" /> : <Wrench size={13} />}
                        {t.pending ? <span className="shimmer">Working through the graph</span> : <span>Used {t.steps.length} graph tool{t.steps.length === 1 ? "" : "s"}</span>}
                      </summary>
                      <ol className="mt-2 space-y-1.5 border-l border-line pl-3">
                        {t.steps.map((st, k) => (
                          <li key={k} className="flex items-start gap-2 font-mono text-[11.5px] text-ink-soft">
                            <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-success" />
                            <span className="break-all">{st.tool}({Object.values(st.args).map((v) => JSON.stringify(v)).join(", ")})</span>
                          </li>
                        ))}
                        {t.pending && <li className="text-[11.5px] text-faint">On a laptop CPU each step takes a while; on the DGX, seconds.</li>}
                      </ol>
                    </details>
                  )}
                  {t.error && <div className="rounded-xl border border-warn/25 bg-warn/[0.07] p-3 text-[13px] text-warn">{t.error}</div>}
                  {t.warnings?.map((w) => <div key={w} className="rounded-xl border border-danger/25 bg-danger/[0.07] p-3 text-[13px] text-danger">{w}</div>)}
                  {t.answer && <div className="whitespace-pre-wrap text-[14.5px] leading-relaxed text-ink">{t.answer}</div>}
                  {t.sources && t.sources.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      {t.sources.map((src, k) => (
                        <button key={src} onClick={() => onOpen?.(src)}
                                className="flex items-center gap-1.5 rounded-full border border-line bg-panel px-2.5 py-1 text-[12px] text-ink-soft transition hover:border-line2 hover:text-ink">
                          <span className="num grid h-4 w-4 place-items-center rounded-full bg-elev-strong text-[10px]">{k + 1}</span>
                          <FileText size={11} /> {src.split("/").pop()}
                        </button>
                      ))}
                    </div>
                  )}
                  {t.drafts?.map((d, k) => <DraftTask key={k} d={d} />)}
                  {t.trace && t.trace.length > 0 && (
                    <details className="text-[12px] text-muted"><summary className="cursor-pointer hover:text-ink">{t.trace.length} Cypher queries behind this answer</summary>
                      {t.trace.map((x, k) => <pre key={k} className="mt-1.5 overflow-x-auto rounded-lg border border-line bg-bg-raised p-2.5 font-mono text-[11px]">{`// ${x.name} · ${x.rows} rows · ${x.ms} ms\n${x.cypher}`}</pre>)}
                    </details>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); if (q.trim() && !busy) ask(q.trim()); }} className="border-t border-line p-3 lg:px-8 lg:py-4">
          <div className={`flex items-end gap-2 rounded-2xl border bg-panel p-1.5 pl-4 shadow-[var(--shadow)] transition focus-within:border-line2 ${thinking ? "ai-ring border-transparent" : "border-line"}`}>
            <textarea value={q} onChange={(e) => setQ(e.target.value)} rows={1}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (q.trim() && !busy) ask(q.trim()); } }}
                      placeholder={turns.length ? "Ask a follow-up…" : "Ask about Flyvi's people, projects, products, customers and decisions"}
                      className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent py-2.5 text-[14px] outline-none" style={{ background: "transparent" }} />
            <button disabled={busy || !q.trim()} aria-label="Send"
                    className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent text-accent-ink transition hover:bg-accent-hover disabled:opacity-35">
              {busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowUp size={16} />}
            </button>
          </div>
          <div className="mt-1.5 px-1 text-[11px] text-faint">Enter to send · Shift+Enter for a new line · answers follow what {"you"} are allowed to see</div>
        </form>
      </div>
    </section>
  );
}
