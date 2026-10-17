"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import {
  ArrowRight, ArrowUpRight, Brain, CalendarOff, Compass, FolderKanban, KanbanSquare, MessageSquareWarning, PackageSearch, Radar, Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import RippleGraph from "@/components/RippleGraph";
import { startTour } from "@/components/Tour";
import { PageTitle, Pill, Section, Stagger, Ticker, riseItem } from "@/components/ui";
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
  notice: { icon: PackageSearch, label: "Supplier change", chip: "bg-accent/12 text-accent", href: (s: Signal) => `/impact?source=${encodeURIComponent(s.id)}` },
  escalation: { icon: MessageSquareWarning, label: "Customer escalation", chip: "bg-danger/12 text-danger", href: (s: Signal) => `/customers?id=${s.subject}` },
  leave: { icon: CalendarOff, label: "People change", chip: "bg-warn/14 text-warn", href: (s: Signal) => `/people?id=${s.subject}&absence=1` },
};

const PROMPTS = [
  "What breaks if NB54360 goes to ₹320 and 22 weeks?",
  "Who covers for Raghavendra in November?",
  "Why is Konkan Naval unhappy?",
];

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default function Overview() {
  const router = useRouter();
  const [me, setMe] = useState<{ name: string } | null>(null);
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [board, setBoard] = useState<Board | null>(null);
  const [risk, setRisk] = useState<Risk | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [feed, setFeed] = useState<Feed | null>(null);
  const [q, setQ] = useState("");
  const [hello, setHello] = useState({ text: "Welcome", date: "" });

  useEffect(() => {
    setTimeout(() => setHello({
      text: greeting(),
      date: new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" }),
    }), 0);
    api<{ name: string }>("/api/viewer").then(setMe).catch(() => {});
    api<Signal[]>("/api/signals").then(setSignals);
    api<Board>("/api/board").then(setBoard);
    api<Risk>("/api/risk").then(setRisk);
    api<Project[]>("/api/projects").then(setProjects);
    api<Feed>("/api/changes").then(setFeed);
  }, []);
  const p = board?.pipeline;
  const open = signals?.filter((s) => !s.investigation).length ?? 0;
  const ask = (text: string) => text.trim() && router.push(`/brain?ask=${encodeURIComponent(text.trim())}`);

  return (
    <Stagger className="space-y-6">
      <motion.section variants={riseItem} className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="text-[13px] text-muted">{hello.date}</div>
          <PageTitle className="mt-1">{`${hello.text}${me?.name ? "," : ""}`}{me?.name ? " " : ""}{me?.name ? <em>{me.name}</em> : null}</PageTitle>
          <p className="mt-1.5 text-[15px] text-muted">
            {signals === null ? "Reading the company graph…" : open
              ? <>{open} signal{open === 1 ? "" : "s"} need{open === 1 ? "s" : ""} a decision. Each is traced through Flyvi&apos;s people, products, orders and decisions.</>
              : "Nothing is waiting on a decision. Everything below is up to date."}
          </p>
        </div>
        <button onClick={startTour} className="flex items-center gap-2 rounded-full border border-line bg-elev px-4 py-2 text-[13.5px] font-medium transition hover:border-line2">
          <Compass size={15} className="text-accent" /> Take the 3-minute tour
        </button>
      </motion.section>

      <motion.div variants={riseItem}><RippleGraph /></motion.div>

      <motion.form variants={riseItem} onSubmit={(e) => { e.preventDefault(); ask(q); }}
                   className="ai-ring card overflow-visible rounded-2xl p-1.5">
        <div className="flex items-center gap-3 px-3">
          <Sparkles size={18} className="shrink-0 text-accent" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask Neura1 anything about Flyvi…"
                 className="h-12 flex-1 bg-transparent text-[15px] outline-none" style={{ background: "transparent" }} />
          <button disabled={!q.trim()} className="flex items-center gap-1.5 rounded-xl bg-accent px-3.5 py-2 text-[13px] font-medium text-accent-ink transition hover:bg-accent-hover disabled:opacity-40">
            Ask <ArrowRight size={14} />
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5 border-t border-line px-3 pb-1.5 pt-2.5">
          {PROMPTS.map((x) => (
            <button key={x} type="button" onClick={() => ask(x)}
                    className="rounded-full border border-line px-2.5 py-1 text-[12.5px] text-muted transition hover:border-line2 hover:bg-elev hover:text-ink">{x}</button>
          ))}
        </div>
      </motion.form>

      <motion.div variants={riseItem}>
        <Section title="Needs attention" icon={Radar} action="All signals" href="/signals" bodyClass="px-2 pb-2 pt-2">
          {signals === null && <div className="space-y-2 p-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-12" />)}</div>}
          <ul className="divide-y divide-line">
            {signals?.map((s) => {
              const k = SIGNAL[s.kind];
              return (
                <li key={s.id}>
                  <Link href={k.href(s)} className="group flex items-center gap-4 rounded-xl px-3 py-3 transition hover:bg-elev">
                    <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${k.chip}`}><k.icon size={17} /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-medium">{s.title}</span>
                      <span className="block truncate text-[12.5px] text-muted">{k.label} · {s.date?.slice(0, 10)} · {s.subject}</span>
                    </span>
                    {s.investigation ? <Pill tone="success" dot>Plan approved</Pill> : <Pill tone="warn" dot>Needs a decision</Pill>}
                    <ArrowUpRight size={16} className="shrink-0 text-faint transition group-hover:text-ink" />
                  </Link>
                </li>
              );
            })}
          </ul>
        </Section>
      </motion.div>

      <motion.div variants={riseItem} className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <Section title="Work in flight" icon={KanbanSquare} action="Workboard" href="/board" className="lg:col-span-5">
          {p ? (
            <>
              <div className="grid grid-cols-4 gap-2">
                {([["To do", p.open, ""], ["In progress", p.in_progress, "text-accent"], ["Blocked", p.blocked, p.blocked ? "text-danger" : ""], ["Done", p.done, "text-success"]] as const).map(([l, n, c]) => (
                  <div key={l}>
                    <Ticker value={n} className={`text-[28px] font-semibold ${c}`} />
                    <div className="text-[12px] text-muted">{l}</div>
                  </div>
                ))}
              </div>
              <Bar parts={[[p.done, "bg-success"], [p.in_progress, "bg-accent"], [p.blocked, "bg-danger"], [p.open, "bg-elev-strong"]]} />
              <ul className="mt-4 space-y-2">
                {feed?.attention.slice(0, 3).map((a, i) => (
                  <li key={i} className="flex gap-2.5 text-[13px] leading-snug">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warn" />
                    <span className="text-ink-soft"><span className="font-mono text-[12px] text-ink">{a.record}</span> {a.reason}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : <div className="skeleton h-28" />}
        </Section>

        <Section title="Risk radar" icon={Radar} action="Open" href="/risk" className="lg:col-span-7" bodyClass="p-0">
          {risk ? (
            <div className="mt-3 grid grid-cols-2 border-t border-line [&>*:nth-child(-n+2)]:border-b [&>*:nth-child(odd)]:border-r [&>*]:border-line">
              <Metric label="Single-sourced part" value={risk.single_source[0]?.id ?? "None"} tone="text-danger"
                      note={risk.single_source[0] ? `${inr(risk.single_source[0].value_at_risk)} of orders depend on it` : "No single-sourced parts"} />
              <Metric label="Biggest chokepoint" value={risk.chokepoints[0]?.name ?? "—"} tone="text-accent"
                      note={`${risk.chokepoints[0]?.label ?? ""} · most paths in the company run through them`} />
              <Metric label="One-person knowledge" value={`${risk.bus_factor.length} subjects`} tone="text-warn"
                      note={risk.bus_factor.slice(0, 2).map((b) => `${b.id} → ${b.person}`).join(" · ")} />
              <Metric label="Largest customer" value={`${Math.round((risk.concentration[0]?.share ?? 0) * 100)}%`} tone="text-violet"
                      note={`${risk.concentration[0]?.customer ?? ""} of open order value`} />
            </div>
          ) : <div className="m-5 skeleton h-32" />}
        </Section>

        <Section title="Projects" icon={FolderKanban} action="All projects" href="/projects" className="lg:col-span-7" bodyClass="px-2 pb-2 pt-2">
          <ul>
            {projects.map((x) => (
              <li key={x.id}>
                <Link href={`/projects?id=${x.id}`} className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition hover:bg-elev">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-elev text-[12px] font-semibold text-ink-soft">{x.name.slice(0, 2).toUpperCase()}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13.5px] font-medium">{x.name}</span>
                    <span className="block truncate text-[12px] text-muted">Led by {x.lead} · due {x.target_date}</span>
                  </span>
                  <Pill tone={x.status === "active" ? "accent" : "neutral"}>{x.status}</Pill>
                </Link>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Latest in the brain" icon={Brain} action="What's new" href="/changes" className="lg:col-span-5">
          <ol className="relative space-y-3.5 border-l border-line pl-4">
            {feed?.feed.slice(0, 6).map((f, i) => (
              <li key={i} className="relative">
                <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full border-2 border-panel bg-accent" />
                <div className="text-[11.5px] text-faint">{f.at.slice(0, 10)} · {f.kind}</div>
                <div className="truncate text-[13.5px]">{f.what}{f.who ? <span className="text-muted"> · {f.who}</span> : null}</div>
              </li>
            ))}
          </ol>
        </Section>
      </motion.div>
    </Stagger>
  );
}

function Metric({ label, value, note, tone }: { label: string; value: string; note: string; tone: string }) {
  return (
    <div className="min-w-0 px-5 py-4">
      <div className="text-[12px] text-muted">{label}</div>
      <div className={`num mt-1 truncate text-[22px] font-semibold ${tone}`}>{value}</div>
      <div className="mt-0.5 truncate text-[12.5px] text-muted" title={note}>{note}</div>
    </div>
  );
}

function Bar({ parts }: { parts: [number, string][] }) {
  const total = parts.reduce((a, [n]) => a + n, 0) || 1;
  return (
    <div className="mt-4 flex h-1.5 gap-0.5 overflow-hidden rounded-full">
      {parts.filter(([n]) => n > 0).map(([n, c], i) => (
        <motion.span key={i} className={`h-full rounded-full ${c}`} initial={{ width: 0 }} animate={{ width: `${(n / total) * 100}%` }}
                     transition={{ duration: 0.8, delay: 0.1 + i * 0.05, ease: [0.16, 1, 0.3, 1] }} />
      ))}
    </div>
  );
}
