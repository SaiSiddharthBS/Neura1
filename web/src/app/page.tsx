"use client";

import Link from "next/link";
import { ArrowUpRight, Brain, CalendarOff, CircleCheck, FolderKanban, KanbanSquare, MessageSquareWarning, PackageSearch, Radar, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { api, inr } from "@/lib/api";

type Signal = { id: string; kind: "notice" | "escalation" | "leave"; title: string; date: string | null; subject: string | null; investigation: string | null };
type Board = { pipeline: { notices: number; investigations: number; open: number; in_progress: number; blocked: number; done: number } };
type Risk = {
  single_source: { id: string; value_at_risk: number }[];
  bus_factor: { id: string; person: string; share: number; away: string[] }[];
  concentration: { customer: string; share: number }[];
  chokepoints: { id: string; name: string; label: string }[];
};
type Project = { id: string; name: string; status: string; lead: string; target_date: string };
type Feed = { feed: { kind: string; at: string; who: string | null; what: string }[]; attention: { record: string; reason: string }[] };

const SIGNAL = {
  notice: { icon: PackageSearch, label: "Supplier change", tone: "text-cyan", href: (s: Signal) => `/impact?source=${encodeURIComponent(s.id)}` },
  escalation: { icon: MessageSquareWarning, label: "Customer escalation", tone: "text-danger", href: (s: Signal) => `/customers?id=${s.subject}` },
  leave: { icon: CalendarOff, label: "People change", tone: "text-warn", href: (s: Signal) => `/people?id=${s.subject}&absence=1` },
};

export default function Overview() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [board, setBoard] = useState<Board | null>(null);
  const [risk, setRisk] = useState<Risk | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [feed, setFeed] = useState<Feed | null>(null);

  useEffect(() => {
    api<Signal[]>("/api/signals").then(setSignals);
    api<Board>("/api/board").then(setBoard);
    api<Risk>("/api/risk").then(setRisk);
    api<Project[]>("/api/projects").then(setProjects);
    api<Feed>("/api/changes").then(setFeed);
  }, []);
  const p = board?.pipeline;

  return (
    <div className="space-y-5">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-cyan">Flyvi Technologies · company brain</div>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">What needs attention today</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">One graph of Flyvi&apos;s people, projects, products, customers, suppliers, documents and decisions. Every change below is traced through all of it.</p>
        </div>
        <button onClick={() => window.dispatchEvent(new Event("neura1:palette"))}
                className="flex items-center gap-2 rounded-xl border border-line bg-elev px-4 py-2.5 text-sm text-muted hover:border-line2 hover:text-ink">
          <Sparkles size={15} className="text-cyan" /> Ask anything about the company <kbd className="ml-2 rounded border border-line px-1.5 font-mono text-[11px]">⌘K</kbd>
        </button>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        {signals.map((s) => {
          const k = SIGNAL[s.kind];
          return (
            <Link key={s.id} href={k.href(s)} className="card group p-5 hover:border-line2">
              <div className="flex items-center justify-between">
                <span className={`flex items-center gap-2 text-xs font-medium uppercase tracking-wide ${k.tone}`}><k.icon size={15} /> {k.label}</span>
                <ArrowUpRight size={16} className="text-muted transition group-hover:text-ink" />
              </div>
              <div className="mt-3 font-medium leading-snug">{s.title}</div>
              <div className="mt-1 text-xs text-muted">{s.date?.slice(0, 10)} · {s.subject}</div>
              <div className={`mt-4 inline-flex rounded-full px-2.5 py-0.5 text-[11px] ${s.investigation ? "bg-success/15 text-success" : "bg-warn/15 text-warn"}`}>
                {s.investigation ? "Plan approved" : "Needs analysis"}
              </div>
            </Link>
          );
        })}
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="card p-5">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 font-medium"><Radar size={16} className="text-accent-hover" /> Risk radar</span>
            <Link href="/risk" className="text-xs text-muted hover:text-ink">Open →</Link>
          </div>
          {risk && (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <Tile title="Single-sourced part" value={risk.single_source[0]?.id ?? "none"} note={risk.single_source[0] ? `${inr(risk.single_source[0].value_at_risk)} of orders depend on it` : ""} tone="danger" />
              <Tile title="Biggest chokepoint" value={risk.chokepoints[0]?.name ?? "—"} note={`${risk.chokepoints[0]?.label ?? ""} · betweenness centrality`} tone="accent" />
              <Tile title="One-person knowledge" value={`${risk.bus_factor.length} subjects`} note={risk.bus_factor.slice(0, 2).map((b) => `${b.id} → ${b.person}`).join(" · ")} tone="warn" />
              <Tile title="Largest customer" value={`${Math.round((risk.concentration[0]?.share ?? 0) * 100)}%`} note={`${risk.concentration[0]?.customer ?? ""} of open order value`} tone="violet" />
            </div>
          )}
        </div>
        <div className="card p-5">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 font-medium"><KanbanSquare size={16} className="text-accent-hover" /> Work in flight</span>
            <Link href="/board" className="text-xs text-muted hover:text-ink">Workboard →</Link>
          </div>
          {p && (
            <div className="mt-4 grid grid-cols-4 gap-2 text-center">
              {[["To do", p.open, "text-ink"], ["In progress", p.in_progress, "text-accent-hover"], ["Blocked", p.blocked, "text-danger"], ["Done", p.done, "text-success"]].map(([l, n, c]) => (
                <div key={l as string} className="rounded-xl bg-elev py-3"><div className={`text-2xl font-semibold tabular-nums ${c}`}>{n}</div><div className="text-[11px] text-muted">{l}</div></div>
              ))}
            </div>
          )}
          <div className="mt-4 space-y-1.5 text-sm">
            {feed?.attention.slice(0, 3).map((a, i) => (
              <div key={i} className="flex gap-2 text-xs"><CircleCheck size={13} className="mt-0.5 shrink-0 text-warn" /><span><b className="font-mono">{a.record}</b> {a.reason}</span></div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="card p-5">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 font-medium"><FolderKanban size={16} className="text-accent-hover" /> Projects</span>
            <Link href="/projects" className="text-xs text-muted hover:text-ink">All →</Link>
          </div>
          <div className="mt-3 divide-y divide-line">
            {projects.map((x) => (
              <Link key={x.id} href={`/projects?id=${x.id}`} className="flex items-center justify-between gap-3 py-2.5 text-sm hover:text-accent-hover">
                <span>{x.name}<span className="block text-xs text-muted">Lead {x.lead} · target {x.target_date}</span></span>
                <span className="rounded-full bg-elev px-2 py-0.5 text-[11px] text-muted">{x.status}</span>
              </Link>
            ))}
          </div>
        </div>
        <div className="card p-5">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 font-medium"><Brain size={16} className="text-accent-hover" /> Latest in the brain</span>
            <Link href="/changes" className="text-xs text-muted hover:text-ink">What&apos;s new →</Link>
          </div>
          <div className="mt-3 space-y-2.5">
            {feed?.feed.slice(0, 6).map((f, i) => (
              <div key={i} className="text-sm"><span className="text-xs text-muted">{f.at.slice(0, 10)} · {f.kind}</span><div className="truncate">{f.what}{f.who ? <span className="text-muted"> · {f.who}</span> : null}</div></div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Tile({ title, value, note, tone }: { title: string; value: string; note: string; tone: "danger" | "accent" | "warn" | "violet" }) {
  const c = { danger: "text-danger", accent: "text-accent-hover", warn: "text-warn", violet: "text-violet" }[tone];
  return (
    <div className="rounded-xl bg-elev p-3">
      <div className="text-[11px] text-muted">{title}</div>
      <div className={`mt-1 truncate text-lg font-semibold ${c}`}>{value}</div>
      <div className="mt-0.5 truncate text-xs text-muted" title={note}>{note}</div>
    </div>
  );
}
