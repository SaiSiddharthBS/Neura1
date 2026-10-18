"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUpRight, Bot, CheckCircle2, Factory, Loader2, PackageSearch, Play, Sparkles, TrendingUp, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageTitle, Pill } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Agent = { id: string; name: string; channel: string; goal: string; tools: string[];
               last: { at: string; findings: number; new: number } | null };
type Finding = { severity: "high" | "medium" | "low"; ref: string; href: string; text: string };
type Run = { agent: Agent; at: string; findings: Finding[]; new: string[]; posted: boolean; channel: string };

const ICON = { procurement: PackageSearch, production: Factory, engineering: Wrench, sales: TrendingUp } as const;
const TONE = { high: "danger", medium: "warn", low: "neutral" } as const;
const when = (s: string) => new Date(s).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [runs, setRuns] = useState<Record<string, Run>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const load = () => api<Agent[]>("/api/departments").then(setAgents).catch(() => {});
  useEffect(() => { load(); }, []);

  async function run(id: string) {
    setBusy(id);
    try {
      const out = await api<Run[]>(`/api/departments/${id}/run`, { method: "POST" });
      setRuns((r) => ({ ...r, ...Object.fromEntries(out.map((x) => [x.agent.id, x])) }));
      const total = out.reduce((n, x) => n + x.findings.length, 0);
      toast.success(id === "all" ? `All four agents checked in: ${total} items posted to their channels` : `${out[0].agent.name}: ${total} items posted to #${out[0].channel}`);
      load();
    } catch (e) {
      toast.error(e instanceof ApiError ? String((e.body as { detail?: unknown })?.detail ?? e.message) : (e as Error).message);
    } finally { setBusy(null); }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <PageTitle>An agent for every <em>department</em></PageTitle>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            Each department has its own agent in its own harness: a standing goal, the few Neura1 engines it may use, the
            channel it reports to, and the permissions of the person it works for. Every check is done by code over the
            graph, so nothing is invented; the agent looks every time, notices what is new, and tells the team.
          </p>
        </div>
        <button onClick={() => run("all")} disabled={!!busy}
                className="press flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-[13.5px] font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-50">
          {busy === "all" ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />} Run all agents
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {(agents ?? []).map((a, n) => {
          const Icon = ICON[a.id as keyof typeof ICON] ?? Bot;
          const r = runs[a.id];
          return (
            <motion.section key={a.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: n * 0.06 }}
                            className="card flex flex-col p-5">
              <header className="flex items-start gap-3">
                <span className="rounded-xl bg-accent/12 p-2.5 text-accent"><Icon size={18} /></span>
                <div className="min-w-0 flex-1">
                  <div className="text-[15px] font-semibold tracking-tight">{a.name}</div>
                  <div className="mt-0.5 text-[12.5px] text-muted">Reports to <span className="font-mono">#{a.channel}</span>
                    {a.last ? ` · last check ${when(a.last.at)}, ${a.last.findings} item${a.last.findings === 1 ? "" : "s"}` : " · not run yet"}</div>
                </div>
                <button onClick={() => run(a.id)} disabled={!!busy}
                        className="press flex items-center gap-1.5 rounded-full border border-line bg-elev px-3 py-1.5 text-[12.5px] font-medium hover:border-line2 disabled:opacity-50">
                  {busy === a.id ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Run
                </button>
              </header>
              <p className="mt-3 text-[13px] text-ink-soft">{a.goal}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {a.tools.map((t) => <span key={t} className="rounded-full border border-line px-2 py-0.5 font-mono text-[11px] text-muted">{t}</span>)}
              </div>
              <AnimatePresence>
                {r && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="mt-4 overflow-hidden">
                    <div className="mb-2 flex items-center gap-2 text-[12.5px] text-success">
                      <CheckCircle2 size={14} /> {r.findings.length ? `Posted ${r.findings.length} item${r.findings.length === 1 ? "" : "s"} to #${r.channel}` : "Nothing needs attention"}
                      {r.new.length > 0 && r.findings.length > 0 && <span className="text-muted">· {r.new.length} new</span>}
                    </div>
                    <ul className="space-y-2">
                      {r.findings.map((f) => (
                        <li key={f.ref} className="flex items-start gap-2 text-[13px]">
                          <Pill tone={TONE[f.severity]}>{f.severity}</Pill>
                          <span className="min-w-0 flex-1">{f.text}</span>
                          <Link href={f.href} className="shrink-0 text-muted hover:text-ink" aria-label={`Open ${f.ref}`}><ArrowUpRight size={14} /></Link>
                        </li>
                      ))}
                    </ul>
                    <Link href="/chat" className="mt-3 inline-flex items-center gap-1 text-[12.5px] text-accent">See it in #{r.channel} <ArrowUpRight size={12} /></Link>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.section>
          );
        })}
      </div>
    </div>
  );
}
