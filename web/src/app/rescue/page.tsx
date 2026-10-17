"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { Check, CheckCircle2, ChevronRight, Cpu, LifeBuoy, Loader2, Lock, MessageSquareQuote, Quote, SkipForward, Sparkles } from "lucide-react";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { PageTitle, Pill } from "@/components/ui";
import { Avatar } from "@/components/ViewerSwitch";
import { api, ApiError, viewerId } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";

type Question = { id: string; about: string[]; question: string; why: string; answered?: boolean; followup?: boolean };
type Captured = { id: string; question: string; question_id: string; text: string; ts: string; about: string[] };
type Plan = { person: { id: string; name: string }; absence: { start: string | null; end: string | null } | null;
              questions: Question[]; captured: Captured[]; at_risk: { id: string; share: number; next_best: string | null; why: string[] }[] };
type Candidate = { id: string; name: string; reason: string; owns?: string[] };
type Review = { facts: { statement: string; quote: string }[]; followup: string | null; model: string | null; note?: string; dropped?: number };

export default function RescuePage() {
  return <Suspense fallback={null}><Rescue /></Suspense>;
}

function Rescue() {
  const params = useSearchParams();
  const me = useMemo(() => viewerId(), []);
  const [person, setPerson] = useState(params.get("person") ?? "");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [queue, setQueue] = useState<Question[]>([]);
  const [current, setCurrent] = useState(0);
  const [answer, setAnswer] = useState("");
  const [saving, setSaving] = useState(false);
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [reviews, setReviews] = useState<Record<string, Review>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Candidate[]>("/api/rescue/candidates").then((c) => {
      setCandidates(c);
      setPerson((p) => p || c[0]?.id || me);
    }).catch(() => setPerson((p) => p || me));
  }, [me]);

  const load = useCallback(async (pid: string) => {
    try {
      const p = await api<Plan>(`/api/rescue?person=${encodeURIComponent(pid)}`);
      setPlan(p);
      setQueue(p.questions);
      setCurrent(Math.max(0, p.questions.findIndex((q) => !q.answered)));
      setError(null);
    } catch (e) {
      setPlan(null);
      setError(e instanceof ApiError ? String((e.body as { detail?: string })?.detail ?? e.message) : (e as Error).message);
    }
  }, []);
  useEffect(() => { if (person) setTimeout(() => load(person), 0); }, [person, load]);

  const q = queue[current];
  const done = queue.filter((x) => x.answered).length;

  async function save() {
    if (!q || !answer.trim() || !plan) return;
    if (!credentials()) return;
    setSaving(true); setError(null);
    const text = answer.trim();
    try {
      await api("/api/rescue/answer", { method: "POST", write: true, body: JSON.stringify({ person: plan.person.id, question_id: q.id, question: q.question, about: q.about, answer: text }) });
      const updated = queue.map((x, i) => (i === current ? { ...x, answered: true } : x));
      setQueue(updated);
      setCurrent(pick(updated, current));
      setPlan((p) => p && { ...p, captured: [...p.captured, { id: `${q.id}-${Date.now()}`, question: q.question, question_id: q.id, text, ts: new Date().toISOString(), about: q.about }] });
      setAnswer("");
      // The DGX reads the answer: verified facts, and one follow-up if something is missing.
      setReviewing(q.id);
      api<Review>("/api/rescue/review", { method: "POST", body: JSON.stringify({ question: q.question, answer: text }) })
        .then((r) => {
          setReviews((x) => ({ ...x, [q.id]: r }));
          if (r.followup) {
            setQueue((list) => {
              const at = list.findIndex((x) => x.id === q.id);
              const f: Question = { id: `${q.id}:follow`, about: q.about, question: r.followup!, why: "A follow-up from Neura1 after reading your answer", followup: true };
              return list.some((x) => x.id === f.id) ? list : [...list.slice(0, at + 1), f, ...list.slice(at + 1)];
            });
          }
        })
        .catch(() => {})
        .finally(() => setReviewing(null));
    } catch (e) {
      if (e instanceof ApiError && e.status === 403 && String(e.message).toLowerCase().includes("passcode")) forgetPasscode();
      setError(e instanceof ApiError ? String((e.body as { detail?: string })?.detail ?? e.message) : (e as Error).message);
    } finally { setSaving(false); }
  }

  /** The next unanswered question after this one, wrapping round; this one if nothing else is left. */
  function pick(list: Question[], from: number) {
    const after = list.findIndex((x, i) => i > from && !x.answered);
    const first = list.findIndex((x, i) => i !== from && !x.answered);
    return after >= 0 ? after : first >= 0 ? first : from;
  }

  return (
    <div className="space-y-5">
      <div>
        <PageTitle>Knowledge <em>rescue</em></PageTitle>
        <p className="mt-1 max-w-3xl text-sm text-muted">Before someone leaves or goes on long leave, capture what only they know. The questions come from the graph: what they own, what Flyvi relies on them for, and the decisions they were part of. Every answer becomes searchable company knowledge, linked to what it is about.</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="card h-fit p-3">
          <div className="px-1.5 pb-1.5 text-[12px] font-medium text-faint">{candidates.length > 1 ? "Whose knowledge" : "You"}</div>
          {candidates.map((c) => (
            <button key={c.id} onClick={() => setPerson(c.id)} aria-current={c.id === person}
                    className={`flex w-full items-center gap-2.5 rounded-xl px-2 py-2 text-left transition ${c.id === person ? "bg-accent/12 ring-1 ring-accent/25" : "hover:bg-elev"}`}>
              <Avatar name={c.name} size={30} />
              <span className="min-w-0"><span className="block truncate text-[13.5px] font-medium">{c.name}</span>
                <span className={`block truncate text-[11.5px] ${c.reason.startsWith("away") ? "text-warn" : "text-muted"}`}>{c.reason}</span></span>
            </button>
          ))}
        </aside>

        <div className="min-w-0 space-y-4">
          {error && <div className="card flex items-center gap-2 p-4 text-[13px] text-muted"><Lock size={15} /> {error}</div>}
          {plan && (
            <>
              <section className="card flex flex-wrap items-center gap-4 p-5">
                <Avatar name={plan.person.name} size={52} />
                <div className="min-w-0 flex-1">
                  <div className="text-[18px] font-semibold tracking-tight">What only {plan.person.name} knows</div>
                  <div className="text-[13px] text-muted">{plan.absence?.start ? `Away ${plan.absence.start} to ${plan.absence.end}. ` : ""}{done} of {queue.length} questions answered · {plan.captured.length} {plan.captured.length === 1 ? "answer" : "answers"} captured</div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-elev-strong">
                    <motion.div className="h-full rounded-full bg-gradient-to-r from-accent to-violet" animate={{ width: `${queue.length ? (100 * done) / queue.length : 0}%` }} transition={{ type: "spring", stiffness: 120, damping: 22 }} />
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {plan.at_risk.slice(0, 4).map((k) => <Pill key={k.id} tone={k.share >= 0.5 ? "danger" : "warn"}>{k.id} · {Math.round(k.share * 100)}%</Pill>)}
                </div>
              </section>

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
                <section className="card p-5">
                  <AnimatePresence mode="wait">
                    {q ? (
                      <motion.div key={q.id} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}>
                        <div className="flex items-center gap-2 text-[12px] text-muted">
                          <span className="grid h-6 w-6 place-items-center rounded-full bg-gradient-to-br from-accent to-violet text-white"><LifeBuoy size={13} /></span>
                          Question {current + 1} of {queue.length}
                          {q.followup && <Pill tone="violet"><Sparkles size={11} /> follow-up</Pill>}
                          {q.answered && <Pill tone="success">answered</Pill>}
                        </div>
                        <h2 className="mt-3 text-[17px] font-semibold leading-snug tracking-tight">{q.question}</h2>
                        <div className="mt-1.5 text-[12px] text-muted">Why this question: {q.why}</div>
                        <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} rows={6} placeholder="Answer in your own words: values, steps, gotchas, who to call…"
                                  onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save(); }}
                                  className="mt-4 w-full resize-y rounded-2xl border border-line px-4 py-3 text-[14px] leading-relaxed outline-none focus:border-accent/50" />
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <button onClick={save} disabled={saving || !answer.trim()} className="press flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-[13.5px] font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-40">
                            {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Save as company knowledge
                          </button>
                          <button onClick={() => { setAnswer(""); setCurrent(pick(queue, current)); }} className="flex items-center gap-1 rounded-xl px-3 py-2 text-[13px] text-muted hover:bg-elev"><SkipForward size={14} /> Skip</button>
                          <span className="ml-auto text-[11.5px] text-faint">⌘ Enter to save</span>
                        </div>
                      </motion.div>
                    ) : (
                      <div className="py-10 text-center text-[14px] text-muted"><CheckCircle2 size={22} className="mx-auto mb-2 text-success" />Nothing left to ask.</div>
                    )}
                  </AnimatePresence>
                </section>

                <aside className="card h-fit p-3">
                  <div className="px-1.5 pb-1 text-[12px] font-medium text-faint">Interview</div>
                  <ol className="space-y-0.5">
                    {queue.map((x, i) => (
                      <li key={x.id}>
                        <button onClick={() => { setCurrent(i); setAnswer(""); }}
                                className={`flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-[12.5px] transition ${i === current ? "bg-elev-strong" : "hover:bg-elev"} ${x.followup ? "pl-6" : ""}`}>
                          {x.answered ? <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-success" /> : <ChevronRight size={14} className="mt-0.5 shrink-0 text-faint" />}
                          <span className="line-clamp-2 text-ink-soft">{x.question}</span>
                        </button>
                      </li>
                    ))}
                  </ol>
                  {reviewing && <div className="mt-2 flex items-center gap-2 px-2 text-[11.5px] text-muted"><Cpu size={12} className="text-accent" /><Loader2 size={12} className="animate-spin" /> Reading the answer on the DGX…</div>}
                </aside>
              </div>

              {plan.captured.length > 0 && (
                <section className="card p-5">
                  <h2 className="flex items-center gap-2 text-[14px] font-semibold"><MessageSquareQuote size={15} className="text-muted" /> Captured, and now part of the company graph</h2>
                  <div className="mt-3 space-y-3">
                    {[...plan.captured].reverse().map((c) => {
                      const r = reviews[c.question_id];
                      return (
                        <motion.div key={c.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl border border-line bg-elev/40 p-4">
                          <div className="text-[12px] text-muted">{c.question}</div>
                          <p className="mt-1 whitespace-pre-wrap text-[14px] leading-relaxed">{c.text}</p>
                          <div className="mt-2 flex flex-wrap items-center gap-1 text-[11px] text-muted">linked to
                            {c.about.map((a) => <Link key={a} href={`/explore?id=${encodeURIComponent(a)}`} className="rounded bg-elev px-1.5 py-0.5 font-mono text-ink-soft hover:bg-accent/15">{a}</Link>)}
                          </div>
                          {r && r.facts.length > 0 && (
                            <div className="mt-3 border-t border-line pt-2.5">
                              <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-muted"><Sparkles size={12} className="text-accent" /> What Neura1 took from it, each checked word for word{r.model ? ` · ${r.model}` : ""}</div>
                              <ul className="mt-1.5 space-y-1">
                                {r.facts.map((f) => (
                                  <li key={f.quote} className="flex gap-2 text-[12.5px]"><Quote size={11} className="mt-1 shrink-0 text-faint" /><span><span className="text-ink">{f.statement}</span> <span className="text-faint">“{f.quote}”</span></span></li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </motion.div>
                      );
                    })}
                  </div>
                  <p className="mt-3 text-[12px] text-muted">Ask &amp; search, chat and the sandbox now use these answers. <Link href="/brain" className="text-accent hover:underline">Ask something about it →</Link></p>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
