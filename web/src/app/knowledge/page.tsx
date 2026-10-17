"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { CalendarX, CheckCircle2, ChevronDown, Clock3, FileText, HeartPulse, Loader2, Quote, Send, ShieldAlert, TimerReset } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageTitle, Pill, Ticker } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";

type Finding = {
  kind: "contradicts" | "lead_time" | "away" | "superseded"; severity: "high" | "medium" | "low"; title: string; message: string;
  passage: string; quote: string; line: string; record: string | null; evidence: string[]; person: string | null;
};
type Doc = { id: string; title: string; kind: string; owner: string | null; owner_id: string | null; reviewed: string | null; findings: Finding[]; passages: number };
type Report = { documents: Doc[]; findings: number; healthy: number; checked: number; today: string };

const ICON = { contradicts: ShieldAlert, lead_time: TimerReset, away: CalendarX, superseded: Clock3 } as const;
const KIND = { contradicts: "Contradicts the records", lead_time: "Lead time out of date", away: "Routes work to someone away", superseded: "Changed since last review" } as const;

/** The sentence with the stale words marked. */
function Marked({ line, quote }: { line: string; quote: string }) {
  const at = line.indexOf(quote);
  if (at < 0) return <>{line}</>;
  return <>{line.slice(0, at)}<mark className="rounded bg-danger/20 px-0.5 text-ink">{quote}</mark>{line.slice(at + quote.length)}</>;
}

export default function KnowledgeHealth() {
  const [r, setR] = useState<Report | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [asking, setAsking] = useState<string | null>(null);
  const [asked, setAsked] = useState<Record<string, string>>({});

  useEffect(() => {
    api<Report>("/api/knowledge-health").then((x) => { setR(x); setOpen(x.documents.find((d) => d.findings.length)?.id ?? null); }).catch(() => {});
  }, []);

  async function ask(d: Doc) {
    if (!credentials()) return;
    setAsking(d.id);
    try {
      const t = await api<{ id: string; owner: string | null }>("/api/knowledge-health/review", { method: "POST", write: true, body: JSON.stringify({ source: d.id }) });
      setAsked((x) => ({ ...x, [d.id]: t.id }));
      toast.success(d.owner ? `Asked ${d.owner} to update it` : "Task created", { description: `${d.title} · on the Workboard` });
    } catch (e) {
      const msg = e instanceof ApiError && e.body && typeof e.body === "object" && "detail" in e.body ? String((e.body as { detail: unknown }).detail) : (e as Error).message;
      if (e instanceof ApiError && e.status === 403 && msg.toLowerCase().includes("passcode")) forgetPasscode();
      toast.error(msg);
    } finally { setAsking(null); }
  }

  return (
    <div className="space-y-5">
      <div>
        <PageTitle>Is what Flyvi <em>knows</em> still true?</PageTitle>
        <p className="mt-1 max-w-3xl text-sm text-muted">Handbooks, procedures, guides and documents written in Neura1 are checked, sentence by sentence, against what the graph knows today: decisions, quotes, supplier notices, revisions and who is away. Meeting notes and reports are records of their day and are left as they are. Rules, no model; every finding quotes the exact words.</p>
      </div>

      {!r && <div className="card grid h-40 place-items-center text-muted"><Loader2 className="animate-spin" size={18} /></div>}
      {r && (
        <>
          <div className="grid grid-cols-3 gap-2.5">
            <div className="card p-3.5"><div className="text-[11.5px] text-muted">Living documents checked</div><div className="mt-1 text-[22px] font-semibold"><Ticker value={r.checked} /></div></div>
            <div className="card p-3.5"><div className="text-[11.5px] text-muted">Out-of-date facts</div><div className={`mt-1 text-[22px] font-semibold ${r.findings ? "text-danger" : ""}`}><Ticker value={r.findings} /></div></div>
            <div className="card p-3.5"><div className="text-[11.5px] text-muted">Healthy documents</div><div className="mt-1 text-[22px] font-semibold text-success"><Ticker value={r.healthy} /></div></div>
          </div>

          <div className="space-y-3">
            {r.documents.map((d, i) => {
              const sick = d.findings.length > 0;
              const isOpen = open === d.id;
              const high = d.findings.filter((f) => f.severity === "high").length;
              return (
                <motion.section key={d.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.04, 0.3) }}
                                className={`card overflow-hidden ${sick ? "" : "opacity-90"}`}>
                  <button onClick={() => setOpen(isOpen ? null : d.id)} disabled={!sick} aria-expanded={isOpen}
                          className="flex w-full items-center gap-3 px-5 py-4 text-left">
                    <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${sick ? (high ? "bg-danger/12 text-danger" : "bg-warn/12 text-warn") : "bg-success/12 text-success"}`}>
                      {sick ? <HeartPulse size={17} /> : <CheckCircle2 size={17} />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14.5px] font-semibold">{d.title}</span>
                      <span className="block text-[12px] text-muted">{d.owner ? `Maintained by ${d.owner}` : "No owner named"}{d.reviewed ? ` · last reviewed ${d.reviewed}` : ""}{d.kind === "document" ? " · Neura1 Docs" : ""}</span>
                    </span>
                    {sick ? <Pill tone={high ? "danger" : "warn"}>{d.findings.length} out of date</Pill> : <Pill tone="success">Healthy</Pill>}
                    {sick && <ChevronDown size={16} className={`text-faint transition-transform ${isOpen ? "rotate-180" : ""}`} />}
                  </button>
                  <AnimatePresence initial={false}>
                    {isOpen && (
                      <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }} className="overflow-hidden">
                        <div className="space-y-2.5 border-t border-line px-5 py-4">
                          {d.findings.map((f) => {
                            const Icon = ICON[f.kind];
                            return (
                              <div key={`${f.passage}-${f.quote}-${f.title}`} className="rounded-2xl border border-line bg-elev/40 p-3.5">
                                <div className="flex items-start gap-2.5">
                                  <Icon size={16} className={`mt-0.5 shrink-0 ${f.severity === "high" ? "text-danger" : "text-warn"}`} />
                                  <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-2 text-[13.5px] font-medium">{f.title}<span className="text-[11px] font-normal text-faint">{KIND[f.kind]}</span></div>
                                    <div className="mt-1.5 flex gap-2 rounded-xl bg-panel px-3 py-2 text-[13px] text-ink-soft"><Quote size={12} className="mt-1 shrink-0 text-faint" /><span><Marked line={f.line} quote={f.quote} /></span></div>
                                    <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted">{f.message}</p>
                                    {f.record && <Link href={f.record.startsWith("P-") ? `/people?id=${f.record}` : `/explore?id=${encodeURIComponent(f.record)}`} className="mt-1 inline-block text-[12px] text-accent hover:underline">Open {f.record.startsWith("inbox/") ? "the notice" : f.record} →</Link>}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                          <div className="flex flex-wrap items-center gap-2 pt-1">
                            <span className="flex items-center gap-1.5 text-[12px] text-muted"><FileText size={13} /> {d.passages} passages checked</span>
                            {asked[d.id]
                              ? <span className="ml-auto flex items-center gap-1.5 text-[12.5px] text-success"><CheckCircle2 size={14} /> Task {asked[d.id]} is on the Workboard</span>
                              : <button onClick={() => ask(d)} disabled={asking === d.id}
                                        className="press ml-auto flex items-center gap-1.5 rounded-xl bg-accent px-3.5 py-1.5 text-[12.5px] font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-50">
                                  {asking === d.id ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Ask {d.owner ?? "the owner"} to update it</button>}
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.section>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
