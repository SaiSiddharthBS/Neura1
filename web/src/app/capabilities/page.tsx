"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { Lock, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Avatar } from "@/components/ViewerSwitch";
import { PageTitle, Pill, Section, Ticker, type Tone } from "@/components/ui";
import { api } from "@/lib/api";

type Person = { id: string; name: string; level: "hands-on" | "involved" };
type Skill = {
  skill: string; area: string; status: "gap" | "thin" | "unproven" | "covered" | "idle";
  hands_on: number; involved: number; stated: number; open_tasks: number; finished_tasks: number;
  projects: string[]; away_soon: number | null; people: Person[]; examples: string[];
};
type Area = { area: string; skills: number; people: number; active: number; open_tasks: number; finished_tasks: number;
              gaps: number; thin: number; unproven: number; trend: "growing" | "steady" | "quiet" };
type Map = { areas: Area[]; skills: Skill[]; visibility: "names" | "your reports" | "counts"; grid_names: boolean; note: string };

const STATUS: Record<Skill["status"], { label: string; tone: Tone; help: string }> = {
  gap: { label: "Gap", tone: "danger", help: "Work needs it and nobody has it at any level" },
  thin: { label: "One person", tone: "warn", help: "Only one person holds it" },
  unproven: { label: "Unproven", tone: "violet", help: "People are on it, but nobody has finished work in it yet" },
  covered: { label: "Covered", tone: "success", help: "More than one person, with finished work" },
  idle: { label: "No open work", tone: "neutral", help: "Nothing in flight needs it right now" },
};

export default function Capabilities() {
  const [m, setM] = useState<Map | null>(null);
  useEffect(() => { api<Map>("/api/capabilities").then(setM); }, []);
  const byArea = useMemo(() => {
    const g: Record<string, Skill[]> = {};
    m?.skills.forEach((s) => (g[s.area] ??= []).push(s));
    return g;
  }, [m]);
  const attention = m?.skills.filter((s) => s.status === "gap" || s.status === "thin" || (s.status === "unproven" && s.open_tasks >= 2)) ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <PageTitle>What Flyvi is <em>good at</em></PageTitle>
          <p className="mt-1.5 max-w-3xl text-[15px] text-muted">
            Capability built from recorded work: every task is tagged with the skills it needs, and people count where they have
            finished or are doing that work. Evidence, not ratings: no scores or rankings are kept.
          </p>
        </div>
        {m && (
          <span className="flex items-center gap-1.5 rounded-full border border-line bg-elev px-3 py-1 text-[12px] text-muted">
            <Lock size={12} /> {m.visibility === "names" ? "You see names (HR and leadership)" : m.visibility === "your reports" ? "You see names of your reports" : "You see counts; names are private"}
          </span>
        )}
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {!m && [0, 1, 2].map((i) => <div key={i} className="card skeleton h-36" />)}
        {m?.areas.filter((a) => a.open_tasks + a.finished_tasks > 0).map((a, i) => {
          const total = a.open_tasks + a.finished_tasks || 1;
          return (
            <motion.a key={a.area} href={`#${a.area.replace(/\W+/g, "-")}`} className="card card-hover block p-5"
                      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05, duration: 0.45, ease: [0.16, 1, 0.3, 1] }}>
              <div className="flex items-start justify-between gap-2">
                <div className="text-[15px] font-semibold tracking-tight">{a.area}</div>
                {a.trend === "growing" ? <Pill tone="accent"><TrendingUp size={12} /> More ahead than done</Pill>
                  : <Pill>{a.trend === "steady" ? "Steady" : "Quiet"}</Pill>}
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div><Ticker value={a.people} className="text-[26px] font-semibold" /><div className="text-[12px] text-muted">people with finished work</div></div>
                <div><Ticker value={a.active} className="text-[26px] font-semibold text-ink-soft" /><div className="text-[12px] text-muted">people active now</div></div>
              </div>
              <div className="mt-4 flex h-1.5 overflow-hidden rounded-full bg-elev-strong">
                <motion.span className="h-full bg-success" initial={{ width: 0 }} animate={{ width: `${(a.finished_tasks / total) * 100}%` }} transition={{ duration: 0.8, delay: 0.15 }} />
                <motion.span className="h-full bg-accent" initial={{ width: 0 }} animate={{ width: `${(a.open_tasks / total) * 100}%` }} transition={{ duration: 0.8, delay: 0.25 }} />
              </div>
              <div className="mt-1.5 flex justify-between text-[11.5px] text-muted"><span>{a.finished_tasks} done</span><span>{a.open_tasks} open</span></div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {a.thin > 0 && <Pill tone="warn">{a.thin} one-person</Pill>}
                {a.unproven > 0 && <Pill tone="violet">{a.unproven} unproven</Pill>}
                {a.gaps > 0 && <Pill tone="danger">{a.gaps} gap{a.gaps === 1 ? "" : "s"}</Pill>}
              </div>
            </motion.a>
          );
        })}
      </section>

      <Section title="Where Flyvi is thin" icon={TrendingUp} bodyClass="px-2 pb-2 pt-2">
        <p className="px-3 pb-2 text-[13px] text-muted">Skills that open work or active projects need, held by one person or not yet proven by finished work.</p>
        <ul className="divide-y divide-line">
          {attention.map((s) => (
            <li key={s.skill} className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl px-3 py-3">
              <div className="min-w-[220px] flex-1">
                <div className="text-[14px] font-medium">{s.skill}</div>
                <div className="text-[12px] text-muted">{s.area} · {s.open_tasks} open task{s.open_tasks === 1 ? "" : "s"}{s.projects.length ? ` · needed by ${s.projects.join(", ")}` : ""}</div>
              </div>
              <span title={STATUS[s.status].help}><Pill tone={STATUS[s.status].tone} dot>{STATUS[s.status].label}</Pill></span>
              <People s={s} />
              {s.away_soon ? <Pill tone="warn">{s.away_soon} of them away in the next 60 days</Pill> : null}
            </li>
          ))}
          {m && !attention.length && <li className="px-3 py-4 text-sm text-muted">Every skill that open work needs is held by more than one person.</li>}
        </ul>
      </Section>

      {m && Object.entries(byArea).map(([area, skills]) => (
        <Section key={area} title={<span id={area.replace(/\W+/g, "-")} className="scroll-mt-20">{area}</span>} bodyClass="px-2 pb-2 pt-1">
          <div className="grid grid-cols-[minmax(180px,1.4fr)_120px_minmax(140px,1fr)_minmax(160px,1.6fr)] gap-x-4 px-3 pb-1 text-[11.5px] text-faint max-md:hidden">
            <span>Skill</span><span>Status</span><span>Finished · active · stated</span><span>People</span>
          </div>
          <ul className="divide-y divide-line">
            {skills.map((s) => (
              <li key={s.skill} className="grid items-center gap-x-4 gap-y-1 rounded-lg px-3 py-2.5 md:grid-cols-[minmax(180px,1.4fr)_120px_minmax(140px,1fr)_minmax(160px,1.6fr)]">
                <span className="text-[13.5px]">{s.skill}</span>
                <span title={STATUS[s.status].help}><Pill tone={STATUS[s.status].tone}>{STATUS[s.status].label}</Pill></span>
                <span className="num flex items-center gap-1.5 text-[12.5px] text-muted">
                  <Dots n={s.hands_on} className="bg-success" /><Dots n={s.involved} className="bg-accent" /><Dots n={s.stated} className="bg-line2" />
                  <span className="ml-1">{s.hands_on} · {s.involved} · {s.stated}</span>
                </span>
                <People s={s} />
              </li>
            ))}
          </ul>
        </Section>
      ))}

      {m && <p className="text-center text-[12px] text-faint">{m.note} Tags are made by the model from Flyvi&apos;s own skill list and checked by code. Open anyone&apos;s profile in <Link href="/people" className="underline">People</Link> for the work behind it.</p>}
    </div>
  );
}

function Dots({ n, className }: { n: number; className: string }) {
  return <span className="flex gap-0.5">{Array.from({ length: Math.min(n, 6) }).map((_, i) => <span key={i} className={`h-2 w-2 rounded-full ${className}`} />)}</span>;
}

function People({ s }: { s: Skill }) {
  if (!s.people.length) return <span className="text-[12px] text-faint">{s.hands_on + s.involved ? `${s.hands_on + s.involved} ${s.hands_on + s.involved === 1 ? "person" : "people"}` : "Nobody yet"}</span>;
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {s.people.map((p) => (
        <Link key={p.id} href={`/people?id=${p.id}`} title={p.level === "hands-on" ? "Finished work in this" : "Working on this now"}
              className={`flex items-center gap-1.5 rounded-full border py-0.5 pl-0.5 pr-2 text-[12px] transition hover:border-line2 ${p.level === "hands-on" ? "border-success/30" : "border-line border-dashed"}`}>
          <Avatar name={p.name} size={18} /> {p.name}
        </Link>
      ))}
    </span>
  );
}
