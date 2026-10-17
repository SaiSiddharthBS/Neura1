"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import {
  AudioLines, Check, CheckCircle2, Cpu, FileAudio, Gavel, ListChecks, Loader2, Mic, Pause, Play, Quote, ShieldCheck, Sparkles, Upload, XCircle,
} from "lucide-react";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { PageTitle, Pill } from "@/components/ui";
import { Avatar } from "@/components/ViewerSwitch";
import { api, ApiError, viewerId } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";

const savedPasscode = () => { try { return localStorage.getItem("neura1-passcode") ?? ""; } catch { return ""; } };

type Item = { id: string; status: string; title: string; seconds: number | null; at: string; decisions: number; actions: number; error?: string | null };
type Passage = { id: string; text: string; start: number; end: number; about: { id: string; label: string; name: string }[] };
type Decision = { id: string; outcome: string; summary: string; reason: string | null; subject: string | null; instead_of: string | null; at: number | null; evidence: { chunk: string; quote: string; at: number | null }[] };
type Action = { id: string; task: string; due: string | null; quote: string; owner: string | null; owner_id: string | null; at: number | null };
type Meeting = {
  id: string; status: "ready" | "processing"; title: string; audio?: string; seconds?: number; engine?: string; recorded_at?: string; by?: string;
  passages?: Passage[]; decisions?: Decision[]; actions?: Action[];
  stage?: string; error?: string | null; job?: { stage: string; note?: string; result?: { rejected: number; model?: string } } | null;
};

const STAGES = [
  { key: "saved", label: "Saved on Flyvi's machine" },
  { key: "transcribing", label: "Transcribing with open-source Whisper, primed with Flyvi's names and part numbers" },
  { key: "linking", label: "Fixing identifiers and linking every passage to the graph" },
  { key: "reading", label: "The DGX reads it for decisions and action items" },
  { key: "checking", label: "Checking every quote word for word against the transcript" },
  { key: "done", label: "Done" },
];
const clock = (s: number | null | undefined) => (s == null ? "" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`);
const OUTCOME: Record<string, "success" | "danger" | "accent" | "neutral"> = { approved: "success", rejected: "danger", proposed: "accent" };

export default function MeetingsPage() {
  return <Suspense fallback={null}><Meetings /></Suspense>;
}

function Meetings() {
  const params = useSearchParams();
  const router = useRouter();
  const current = params.get("id");
  const [list, setList] = useState<Item[]>([]);
  const [m, setM] = useState<Meeting | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [title, setTitle] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const loadList = useCallback(() => api<Item[]>("/api/meetings").then(setList).catch(() => {}), []);
  useEffect(() => { const t = setTimeout(loadList, 0); return () => clearTimeout(t); }, [loadList]);

  // Follow the selected meeting; while it is being processed, poll.
  useEffect(() => {
    if (!current) { setTimeout(() => setM(null), 0); return; }
    let stop = false, timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const x = await api<Meeting>(`/api/meetings/${encodeURIComponent(current)}`);
        if (stop) return;
        setM(x);
        const busy = x.status === "processing" || (x.job && !["done", "failed"].includes(x.job.stage));
        if (busy) timer = setTimeout(tick, 1200); else loadList();
      } catch (e) { if (!stop) setError((e as Error).message); }
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [current, loadList]);

  const open = (id: string) => router.replace(`/meetings?id=${encodeURIComponent(id)}`, { scroll: false });

  async function upload(file: File | null, sample = false) {
    if (!credentials()) return;
    setUploading(true); setError(null);
    try {
      let r: { id: string };
      if (sample) {
        r = await api<{ id: string }>("/api/meetings/sample", { method: "POST", write: true });
      } else {
        if (!file) return;
        const form = new FormData();
        form.append("file", file);
        if (title.trim()) form.append("title", title.trim());
        const res = await fetch("/api/meetings", { method: "POST", body: form, headers: { "x-neura1-as": viewerId(), "x-demo-passcode": savedPasscode() } });
        const body = await res.json().catch(() => null);
        if (!res.ok) throw new ApiError(res.status, body);
        r = body;
      }
      setTitle("");
      await loadList();
      open(r.id);
    } catch (e) {
      const msg = e instanceof ApiError && e.body && typeof e.body === "object" && "detail" in e.body ? String((e.body as { detail: unknown }).detail) : (e as Error).message;
      if (e instanceof ApiError && e.status === 403 && msg.toLowerCase().includes("passcode")) forgetPasscode();
      setError(msg);
    } finally { setUploading(false); }
  }

  const stage = m?.status === "processing" ? m.stage : m?.job?.stage;
  const processing = !!m && (m.status === "processing" || (!!stage && !["done", "failed"].includes(stage) && m.status !== "ready"));

  return (
    <div className="space-y-5">
      <div>
        <PageTitle>Meetings that <em>remember</em></PageTitle>
        <p className="mt-1 max-w-3xl text-sm text-muted">Drop in a recording. It is transcribed on Flyvi&apos;s own hardware with open-source Whisper, linked to the parts, builds and people it mentions, and read by the DGX for decisions and action items, each kept only if its words are in the transcript. Click any of them to hear the moment it was said.</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="space-y-3">
          <section className="card p-4">
            <div className="text-[13.5px] font-semibold">Add a recording</div>
            <input ref={fileRef} type="file" accept="audio/*,.m4a,.mp3,.wav,.aiff,.ogg,.webm,.flac" className="hidden"
                   onChange={(e) => { upload(e.target.files?.[0] ?? null); e.target.value = ""; }} />
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (optional)" maxLength={120} className="mt-2 w-full rounded-xl border border-line px-3 py-2 text-[13px]" />
            <button onClick={() => fileRef.current?.click()} disabled={uploading}
                    onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); upload(e.dataTransfer.files?.[0] ?? null); }}
                    className="mt-2 flex w-full flex-col items-center gap-1.5 rounded-2xl border border-dashed border-line2 px-3 py-5 text-[12.5px] text-muted transition hover:border-accent/50 hover:bg-accent/[0.04] hover:text-ink disabled:opacity-50">
              {uploading ? <Loader2 size={18} className="animate-spin" /> : <Upload size={18} />} Drop an audio file, or click to choose
              <span className="text-[11px] text-faint">m4a, mp3, wav, aiff, ogg, webm or flac · up to 60 MB</span>
            </button>
            <button onClick={() => upload(null, true)} disabled={uploading}
                    className="press mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl bg-accent px-3 py-2 text-[13px] font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-50">
              <Mic size={14} /> Try the sample: BO-0415 build sync</button>
            <p className="mt-1.5 text-[11px] text-faint">The sample is synthetic: a short build meeting read aloud by a speech synthesiser.</p>
            {error && <div className="mt-2 text-[12px] text-warn">{error}</div>}
          </section>
          <section className="card overflow-hidden">
            <div className="px-4 pb-1 pt-3 text-[12px] font-medium text-faint">Recordings</div>
            <ul className="space-y-0.5 px-2 pb-2">
              {list.map((x) => (
                <li key={x.id}>
                  <button onClick={() => open(x.id)} aria-current={x.id === current}
                          className={`flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition ${x.id === current ? "bg-accent/12 ring-1 ring-accent/25" : "hover:bg-elev"}`}>
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-elev-strong text-muted">{x.status === "ready" ? <FileAudio size={15} /> : x.status === "failed" ? <XCircle size={15} className="text-danger" /> : <Loader2 size={15} className="animate-spin" />}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium">{x.title}</span>
                      <span className="block text-[11.5px] text-muted">{x.status === "ready" ? `${clock(x.seconds)} · ${x.decisions} decisions · ${x.actions} actions` : x.status}</span>
                    </span>
                  </button>
                </li>
              ))}
              {!list.length && <li className="px-2.5 py-3 text-[12.5px] text-muted">No recordings yet.</li>}
            </ul>
          </section>
        </aside>

        <div className="min-w-0">
          {!m && (
            <div className="card grid min-h-[420px] place-items-center p-8 text-center">
              <div className="max-w-md space-y-3">
                <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-accent/12 text-accent"><AudioLines size={24} /></span>
                <div className="text-[17px] font-semibold tracking-tight">Nothing said in a meeting gets lost</div>
                <p className="text-[13px] text-muted">The audio and the transcript never leave Flyvi&apos;s machines. Try the sample to see a build meeting turn into verified decisions and owned action items in about a minute.</p>
              </div>
            </div>
          )}
          {m && (processing || stage === "failed") && <Progress m={m} stage={stage ?? "saved"} />}
          {m && m.status === "ready" && !processing && <Ready m={m} />}
        </div>
      </div>
    </div>
  );
}

function Progress({ m, stage }: { m: Meeting; stage: string }) {
  const at = STAGES.findIndex((s) => s.key === stage);
  return (
    <section className="card p-6">
      <div className="flex items-center gap-2 text-[15px] font-semibold"><Sparkles size={16} className="text-accent" /> {m.title}</div>
      <ol className="mt-5 space-y-3.5">
        {STAGES.slice(0, -1).map((s, i) => {
          const done = stage !== "failed" && i < at, now = i === at && stage !== "failed";
          return (
            <motion.li key={s.key} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }} className="flex items-center gap-3 text-[13.5px]">
              <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${done ? "bg-success text-white" : now ? "bg-accent/15 text-accent" : "bg-elev-strong text-faint"}`}>
                {done ? <Check size={14} strokeWidth={3} /> : now ? <Loader2 size={14} className="animate-spin" /> : <span className="text-[11px]">{i + 1}</span>}
              </span>
              <span className={done ? "text-ink-soft" : now ? "font-medium text-ink" : "text-faint"}>{s.label}{s.key === "reading" && <Cpu size={12} className="ml-1.5 inline text-accent" />}</span>
            </motion.li>
          );
        })}
      </ol>
      {stage === "failed" && <div className="mt-4 rounded-xl border border-danger/30 bg-danger/[0.07] p-3 text-[13px] text-danger">{m.error ?? m.job?.note ?? "Processing failed"}</div>}
    </section>
  );
}

function Ready({ m }: { m: Meeting }) {
  const audio = useRef<HTMLAudioElement>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const total = m.seconds ?? 0;
  const passages = m.passages ?? [];
  const active = passages.findIndex((p) => t >= p.start && t < p.end + 0.6);
  const people = new Set((m.passages ?? []).flatMap((p) => p.about.filter((a) => a.label === "Person").map((a) => a.id)));

  const seek = (s: number | null) => {
    const el = audio.current;
    if (!el || s == null) return;
    el.currentTime = Math.max(0, s - 0.2);
    el.play().catch(() => {});
  };
  const speaker = (text: string) => /^([A-Z][a-z]+) here\b/.exec(text)?.[1] ?? null;
  const marks = [
    ...(m.decisions ?? []).map((d) => ({ at: d.at, kind: "decision" as const, label: d.summary })),
    ...(m.actions ?? []).map((a) => ({ at: a.at, kind: "action" as const, label: a.task })),
  ].filter((x) => x.at != null);

  return (
    <div className="space-y-4">
      <section className="card p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-[17px] font-semibold tracking-tight">{m.title}</h2>
          <Pill>{clock(total)}</Pill>
          <Pill tone="success"><ShieldCheck size={11} /> every quote checked</Pill>
          <span className="ml-auto text-[11.5px] text-faint">{m.engine}{m.job?.result?.model ? ` · read by ${m.job.result.model}` : ""}</span>
        </div>
        <audio ref={audio} src={`/api/meetings/${m.id}/audio`} preload="metadata" onTimeUpdate={(e) => setT(e.currentTarget.currentTime)}
               onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
        <div className="mt-4 flex items-center gap-3">
          <button onClick={() => (playing ? audio.current?.pause() : audio.current?.play())} aria-label={playing ? "Pause" : "Play"}
                  className="press grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent text-accent-ink shadow-[0_6px_24px_-8px_var(--accent)]">
            {playing ? <Pause size={18} /> : <Play size={18} className="translate-x-px" />}
          </button>
          <div className="relative h-10 flex-1 cursor-pointer" onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); seek(((e.clientX - r.left) / r.width) * total); }}>
            <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-elev-strong" />
            <motion.div className="absolute left-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-accent" style={{ width: `${total ? (t / total) * 100 : 0}%` }} />
            {marks.map((x, i) => (
              <button key={i} title={x.label} onClick={(e) => { e.stopPropagation(); seek(x.at); }}
                      className={`absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[var(--bg)] transition hover:scale-125 ${x.kind === "decision" ? "bg-danger" : "bg-violet"}`}
                      style={{ left: `${total ? ((x.at as number) / total) * 100 : 0}%` }} />
            ))}
          </div>
          <span className="num w-20 text-right text-[12px] text-muted">{clock(t)} / {clock(total)}</span>
        </div>
        <div className="mt-2 flex gap-4 text-[11.5px] text-muted">
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-danger" /> decision</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-violet" /> action item</span>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <section className="card p-5">
          <h3 className="flex items-center gap-2 text-[14px] font-semibold"><AudioLines size={15} className="text-muted" /> Transcript</h3>
          <ol className="mt-3 space-y-1.5">
            {passages.map((p, i) => {
              const who = speaker(p.text);
              const on = i === active;
              return (
                <li key={p.id}>
                  <button onClick={() => seek(p.start)} className={`flex w-full gap-3 rounded-xl px-2.5 py-2 text-left transition ${on ? "bg-accent/12 ring-1 ring-accent/25" : "hover:bg-elev"}`}>
                    <span className="num mt-0.5 w-10 shrink-0 text-[11.5px] text-faint">{clock(p.start)}</span>
                    {who ? <Avatar name={who} size={24} /> : <span className="h-6 w-6 shrink-0" />}
                    <span className={`min-w-0 flex-1 text-[13.5px] leading-relaxed ${on ? "text-ink" : "text-ink-soft"}`}>
                      {who && <b className="mr-1">{who}</b>}{who ? p.text.replace(/^[A-Z][a-z]+ here,?\s*/, "") : p.text}
                      {p.about.filter((a) => a.id && a.label !== "Person").length > 0 && (
                        <span className="mt-1 flex flex-wrap gap-1">{p.about.filter((a) => a.id && a.label !== "Person").map((a) => (
                          <Link key={a.id} href={`/explore?id=${encodeURIComponent(a.id)}`} onClick={(e) => e.stopPropagation()} className="rounded bg-elev px-1.5 py-0.5 font-mono text-[10.5px] text-muted hover:bg-accent/15 hover:text-ink">{a.id}</Link>
                        ))}</span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
          <p className="mt-2 text-[11.5px] text-faint">{people.size} people recognised; identifiers put back in their graph form by code.</p>
        </section>

        <div className="space-y-4">
          <section className="card p-5">
            <h3 className="flex items-center gap-2 text-[14px] font-semibold"><Gavel size={15} className="text-muted" /> Decisions</h3>
            <div className="mt-3 space-y-2.5">
              {(m.decisions ?? []).map((d, i) => (
                <motion.div key={d.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }} className="rounded-2xl border border-line bg-elev/40 p-3.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Pill tone={OUTCOME[d.outcome] ?? "neutral"}>{d.outcome}</Pill>
                    {d.subject && <Link href={`/explore?id=${encodeURIComponent(d.subject)}`} className="font-mono text-[12px] hover:underline">{d.subject}</Link>}
                    {d.instead_of && <span className="text-[11.5px] text-muted">instead of <span className="font-mono">{d.instead_of}</span></span>}
                    <Link href={`/explore?id=${encodeURIComponent(d.id)}`} className="ml-auto font-mono text-[11px] text-faint hover:text-ink">{d.id}</Link>
                  </div>
                  <div className="mt-1.5 text-[13.5px] font-medium">{d.summary}</div>
                  {d.evidence.map((e) => (
                    <button key={e.chunk + e.quote} onClick={() => seek(e.at)} className="mt-2 flex w-full gap-2 rounded-xl bg-panel px-3 py-2 text-left text-[12.5px] transition hover:ring-1 hover:ring-accent/30">
                      <Quote size={12} className="mt-0.5 shrink-0 text-faint" /><span className="min-w-0 flex-1 text-ink-soft">“{e.quote}”</span>
                      <span className="num flex shrink-0 items-center gap-1 text-accent"><Play size={10} /> {clock(e.at)}</span>
                    </button>
                  ))}
                </motion.div>
              ))}
              {!(m.decisions ?? []).length && <p className="text-[13px] text-muted">No decisions were found{m.job?.note ? `: ${m.job.note}` : "."}</p>}
            </div>
          </section>
          <section className="card p-5">
            <h3 className="flex items-center gap-2 text-[14px] font-semibold"><ListChecks size={15} className="text-muted" /> Action items</h3>
            <ul className="mt-3 space-y-2">
              {(m.actions ?? []).map((a) => (
                <li key={a.id} className="flex items-start gap-2.5 rounded-xl px-1 py-1">
                  {a.owner ? <Avatar name={a.owner} size={26} /> : <CheckCircle2 size={18} className="text-faint" />}
                  <div className="min-w-0 flex-1 text-[13px]">
                    <div><b>{a.owner}</b> · {a.task}{a.due ? <span className="text-muted"> · {a.due}</span> : null}</div>
                    <div className="text-[11.5px] text-faint">“{a.quote}”</div>
                  </div>
                  <button onClick={() => seek(a.at)} className="num flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[12px] text-accent hover:bg-accent/10"><Play size={10} /> {clock(a.at)}</button>
                </li>
              ))}
              {!(m.actions ?? []).length && <li className="text-[13px] text-muted">No action items were found.</li>}
            </ul>
            <AnimatePresence>{(m.job?.result?.rejected ?? 0) > 0 && <p className="mt-2 text-[11.5px] text-faint">{m.job?.result?.rejected} proposal(s) were dropped because their words are not in the transcript.</p>}</AnimatePresence>
          </section>
        </div>
      </div>
    </div>
  );
}
