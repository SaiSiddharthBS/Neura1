"use client";

import { AnimatePresence, motion } from "motion/react";
import {
  AlertTriangle, CalendarRange, CheckCircle2, ChevronDown, ChevronRight, Download, Factory, Flag, ListChecks, Truck, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { PageTitle, Pill, type Tone } from "@/components/ui";
import { api, inr } from "@/lib/api";

type Span = { start: string | null; end: string | null };
type Item = {
  id: string; kind: "task" | "build" | "order"; title: string; owner: string | null; status: string; projects: string[];
  baseline: Span; plan: Span; forecast: Span; deviation_days: number | null; driver: string | null; reasons: string[];
  state: State; links: string[]; milestone?: boolean;
  penalty?: { note: string | null; weeks_late: number; pct: number; value: number; per_week_pct: number; capped: boolean };
};
type Group = {
  id: string; name: string; lead: string | null; status: string; baseline: Span; plan: Span; forecast: Span;
  deviation_days: number | null; state: State; driver: string | null; reasons: string[]; items: Item[];
};
type State = "on_track" | "at_risk" | "late" | "done" | "done_late" | "unconfirmed" | "unscheduled";
type Timeline = {
  today: string; range: Span; groups: Group[]; leave_included: boolean; rules: string[];
  summary: { items: number; late: number; done_late: number; at_risk: number; projects_late: number;
             worst: { id: string; title: string; deviation_days: number; reason: string }[] };
};
type Row = { key: string; group: Group; item?: Item };

const ZOOM = { weeks: 13, months: 3.6, quarters: 1.8 } as const;
type Zoom = keyof typeof ZOOM;
const ROW = 40;
const DEVIATED: State[] = ["late", "done_late", "at_risk", "unconfirmed"];

const STATE: Record<State, { label: string; tone: Tone }> = {
  on_track: { label: "On track", tone: "accent" }, at_risk: { label: "At risk", tone: "warn" },
  late: { label: "Late", tone: "danger" }, done: { label: "Done", tone: "success" },
  done_late: { label: "Done late", tone: "warn" }, unconfirmed: { label: "Not confirmed", tone: "warn" },
  unscheduled: { label: "No dates", tone: "neutral" },
};
const KIND = { task: ListChecks, build: Factory, order: Truck } as const;

const DAY = 86_400_000;
const dayOf = (s: string) => { const [y, m, d] = s.split("-").map(Number); return Date.UTC(y, m - 1, d) / DAY; };
const fmt = (s: string | null) => s ? new Date(s + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—";
const signed = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n)}d`;

function lag(n: number | null) {
  if (n === null) return "no dates";
  if (n === 0) return "on plan";
  const w = Math.abs(n) >= 14 ? `${Math.round(Math.abs(n) / 7)} weeks` : `${Math.abs(n)} days`;
  return n > 0 ? `${w} late` : `${w} early`;
}

export default function TimelinePage() {
  const [t, setT] = useState<Timeline | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState<Zoom>("months");
  const [onlyDeviations, setOnlyDeviations] = useState(false);
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<Timeline>("/api/gantt").then(setT).catch((e: Error) => setError(e.message));
  }, []);

  const scale = useMemo(() => {
    if (!t) return null;
    const first = new Date(dayOf(t.range.start ?? t.today) * DAY);
    const start = Date.UTC(first.getUTCFullYear(), first.getUTCMonth(), 1) / DAY - 7;
    const end = dayOf(t.range.end ?? t.today) + 35;
    const ppd = ZOOM[zoom];
    const months: { x: number; label: string; year: boolean }[] = [];
    const d = new Date(start * DAY);
    let cur = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1) / DAY;
    while (cur < end) {
      const m = new Date(cur * DAY);
      months.push({ x: (cur - start) * ppd, year: m.getUTCMonth() === 0,
                    label: m.toLocaleDateString("en-IN", { month: zoom === "quarters" ? "short" : "long", timeZone: "UTC" })
                      + (m.getUTCMonth() === 0 || months.length === 0 ? ` ${m.getUTCFullYear()}` : "") });
      cur = Date.UTC(m.getUTCFullYear(), m.getUTCMonth() + 1, 1) / DAY;
    }
    const weeks: number[] = [];
    if (zoom === "weeks") for (let w = start + ((8 - new Date(start * DAY).getUTCDay()) % 7); w < end; w += 7) weeks.push((w - start) * ppd);
    return { start, end, ppd, width: (end - start) * ppd, months, weeks, x: (s: string) => (dayOf(s) - start) * ppd };
  }, [t, zoom]);

  const rows = useMemo<Row[]>(() => {
    if (!t) return [];
    const out: Row[] = [];
    for (const g of t.groups) {
      const items = onlyDeviations ? g.items.filter((i) => DEVIATED.includes(i.state)) : g.items;
      if (onlyDeviations && !items.length && (g.deviation_days ?? 0) <= 0) continue;
      out.push({ key: g.id, group: g });
      if (!closed.has(g.id)) for (const i of items) out.push({ key: `${g.id}/${i.id}`, group: g, item: i });
    }
    return out;
  }, [t, onlyDeviations, closed]);

  // Open on today, a month of history to the left.
  useEffect(() => {
    if (!t || !scale || !scroller.current) return;
    scroller.current.scrollTo({ left: Math.max(scale.x(t.today) - 21 * scale.ppd, 0), behavior: "smooth" });
  }, [t, scale]);

  const all = useMemo(() => t?.groups.flatMap((g) => g.items) ?? [], [t]);
  const chosen = selected ? all.find((i) => i.id === selected) ?? t?.groups.find((g) => g.id === selected) ?? null : null;

  function exportCsv() {
    if (!t) return;
    const head = ["id", "kind", "title", "owner", "state", "baseline_end", "plan_end", "forecast_end", "deviation_days", "why"];
    const q = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;
    const lines = [head.join(","), ...all.map((i) => [i.id, i.kind, i.title, i.owner, i.state, i.baseline.end, i.plan.end,
      i.forecast.end, i.deviation_days, i.reasons.join(" ")].map(q).join(","))];
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `neura1-timeline-${t.today}.csv` });
    a.click();
    URL.revokeObjectURL(url);
  }

  if (error) return <div className="card p-6 text-danger">Could not load the timeline: {error}</div>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <PageTitle>The plan, and where it is <em>slipping</em></PageTitle>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            Every project, task, build and customer order on one timeline. The faint outline is the first plan recorded, the
            bar is the plan held now, and red is what the graph says will really happen: worked out by code from stock,
            open purchase orders, supplier notices, lead times and leave.
          </p>
        </div>
        <button onClick={exportCsv} disabled={!t}
                className="press flex items-center gap-2 rounded-full border border-line bg-elev px-4 py-2 text-[13px] font-medium transition hover:border-line2 disabled:opacity-40">
          <Download size={14} /> Export deviations (.csv)
        </button>
      </div>

      {/* Summary */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Items late" value={t?.summary.late} tone="danger" note={t ? `of ${t.summary.items} on the timeline` : ""} />
        <Stat label="Projects past target" value={t?.summary.projects_late} tone="danger" note="by forecast" />
        <Stat label="At risk" value={t?.summary.at_risk} tone="warn" note="on plan, but depends on something late" />
        <Stat label="Finished late" value={t?.summary.done_late} tone="warn" note="done after the due date" />
      </div>

      {t && t.summary.worst.length > 0 && (
        <div className="card p-4">
          <div className="mb-2 flex items-center gap-2 text-[13px] font-semibold"><AlertTriangle size={14} className="text-danger" /> Biggest slips</div>
          <div className="grid gap-2 md:grid-cols-3">
            {t.summary.worst.map((w) => (
              <button key={w.id} onClick={() => setSelected(w.id)}
                      className="lift rounded-xl border border-line bg-elev p-3 text-left transition hover:border-danger/40">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[12px] text-muted">{w.id}</span>
                  <span className="num text-[13px] font-semibold text-danger">{lag(w.deviation_days)}</span>
                </div>
                <div className="mt-1 line-clamp-1 text-[13.5px] font-medium">{w.title}</div>
                <div className="mt-1 line-clamp-2 text-[12px] text-muted">{w.reason}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-full border border-line bg-elev p-0.5 text-[12.5px]">
          {(Object.keys(ZOOM) as Zoom[]).map((z) => (
            <button key={z} onClick={() => setZoom(z)}
                    className={`rounded-full px-3 py-1 capitalize transition ${zoom === z ? "bg-panel font-medium shadow-sm" : "text-muted hover:text-ink"}`}>{z}</button>
          ))}
        </div>
        <button onClick={() => setOnlyDeviations((v) => !v)}
                className={`rounded-full border px-3 py-1 text-[12.5px] transition ${onlyDeviations ? "border-danger/40 bg-danger/10 text-danger" : "border-line bg-elev text-muted hover:text-ink"}`}>
          Only deviations
        </button>
        <div className="ml-auto flex flex-wrap items-center gap-3 text-[11.5px] text-muted">
          <Legend kind="baseline" /> Baseline <Legend kind="plan" /> Plan <Legend kind="late" /> Forecast overrun
          <Legend kind="done" /> Done <span className="inline-block h-2.5 w-2.5 rotate-45 rounded-[2px] bg-ink-soft/70" /> Due date
        </div>
      </div>

      {/* The chart */}
      <div data-tour="gantt" className="card overflow-hidden p-0">
        {!t || !scale ? <div className="h-[420px] animate-pulse bg-elev" /> : (
          <div className="flex">
            <div className="w-[190px] shrink-0 border-r border-line sm:w-[330px]">
              <div className="flex h-12 items-end border-b border-line px-4 pb-2 text-[11px] font-medium uppercase tracking-wider text-faint">Work</div>
              {rows.map((r) => r.item
                ? <ItemLabel key={r.key} item={r.item} active={selected === r.item.id} onClick={() => setSelected(r.item!.id)} />
                : <GroupLabel key={r.key} group={r.group} open={!closed.has(r.group.id)} active={selected === r.group.id}
                              onToggle={() => setClosed((s) => { const n = new Set(s); if (n.has(r.group.id)) n.delete(r.group.id); else n.add(r.group.id); return n; })}
                              onClick={() => setSelected(r.group.id)} />)}
            </div>
            <div ref={scroller} className="relative min-w-0 flex-1 overflow-x-auto" data-lenis-prevent>
              <div className="relative" style={{ width: scale.width }}>
                {/* Scale */}
                <div className="sticky top-0 z-10 h-12 border-b border-line bg-panel/90 backdrop-blur">
                  {scale.months.map((m) => (
                    <div key={m.x} className="absolute bottom-0 top-0 border-l border-line" style={{ left: m.x }}>
                      <span className={`absolute left-2 top-2 whitespace-nowrap text-[11.5px] ${m.year ? "font-semibold text-ink" : "text-muted"}`}>{m.label}</span>
                    </div>
                  ))}
                  {scale.weeks.map((x) => <div key={x} className="absolute bottom-0 h-2 border-l border-line2" style={{ left: x }} />)}
                  <span className="absolute bottom-1.5 -translate-x-1/2 rounded-full bg-accent px-2 py-0.5 text-[10.5px] font-semibold text-accent-ink shadow-[0_0_0_3px_var(--panel)]"
                        style={{ left: scale.x(t.today) }}>Today</span>
                </div>
                {/* Grid, today, rows */}
                <div className="relative" style={{ height: rows.length * ROW }}>
                  {scale.months.map((m) => <div key={m.x} className="absolute inset-y-0 border-l border-line/70" style={{ left: m.x }} />)}
                  {scale.weeks.map((x) => <div key={x} className="absolute inset-y-0 border-l border-dashed border-line/50" style={{ left: x }} />)}
                  {rows.map((r, n) => (
                    <div key={r.key} className={`absolute inset-x-0 ${r.item ? "" : "bg-elev/60"} ${selected && (r.item?.id ?? r.group.id) === selected ? "bg-accent/[0.07]" : ""}`}
                         style={{ top: n * ROW, height: ROW }}>
                      {r.item ? <ItemBars item={r.item} x={scale.x} onClick={() => setSelected(r.item!.id)} />
                              : <GroupBar group={r.group} x={scale.x} />}
                    </div>
                  ))}
                  <Connectors rows={rows} x={scale.x} />
                  <div className="pointer-events-none absolute inset-y-0 z-[5] w-px bg-accent shadow-[0_0_10px_var(--accent)]" style={{ left: scale.x(t.today) }} />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {t && (
        <details className="card group p-4 text-[13px]">
          <summary className="flex cursor-pointer list-none items-center gap-2 font-medium">
            <ChevronRight size={14} className="transition group-open:rotate-90" /> How the forecast is worked out
          </summary>
          <ul className="mt-3 space-y-1.5 pl-6 text-muted">
            {t.rules.map((r) => <li key={r} className="list-disc">{r}</li>)}
            {!t.leave_included && <li className="list-disc">Leave is weighed only for your own work and the people you back up; directors and leadership see all of it.</li>}
          </ul>
        </details>
      )}

      <AnimatePresence>
        {chosen && <Detail key={chosen.id} entry={chosen} all={all} onSelect={setSelected} onClose={() => setSelected(null)} />}
      </AnimatePresence>
    </div>
  );
}

function Stat({ label, value, tone, note }: { label: string; value: number | undefined; tone: "danger" | "warn"; note: string }) {
  return (
    <div className="card p-4">
      <div className="text-[12px] text-muted">{label}</div>
      <div className={`num mt-1 text-[28px] font-semibold leading-none ${value ? (tone === "danger" ? "text-danger" : "text-warn") : "text-ink"}`}>{value ?? "–"}</div>
      <div className="mt-1.5 text-[11.5px] text-faint">{note}</div>
    </div>
  );
}

function Legend({ kind }: { kind: "baseline" | "plan" | "late" | "done" }) {
  const cls = { baseline: "border border-dashed border-ink-soft/60", plan: "bg-accent/80", late: "gantt-overrun", done: "bg-success/75" }[kind];
  return <span className={`inline-block h-2.5 w-5 rounded-full ${cls}`} />;
}

function GroupLabel({ group, open, active, onToggle, onClick }: { group: Group; open: boolean; active: boolean; onToggle: () => void; onClick: () => void }) {
  return (
    <div className={`flex items-center gap-1.5 border-b border-line bg-elev/60 px-2 ${active ? "bg-accent/[0.07]" : ""}`} style={{ height: ROW }}>
      <button onClick={onToggle} aria-label={open ? "Collapse" : "Expand"} className="rounded p-1 text-muted hover:text-ink">
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      <button onClick={onClick} className="flex min-w-0 flex-1 items-center gap-2 text-left">
        <Flag size={13} className={(group.deviation_days ?? 0) > 0 ? "shrink-0 text-danger" : "shrink-0 text-muted"} />
        <span className="truncate text-[13px] font-semibold tracking-tight">{group.name}</span>
        {(group.deviation_days ?? 0) > 0 && <span className="num ml-auto shrink-0 text-[11.5px] font-semibold text-danger">{signed(group.deviation_days!)}</span>}
      </button>
    </div>
  );
}

function ItemLabel({ item, active, onClick }: { item: Item; active: boolean; onClick: () => void }) {
  const Icon = KIND[item.kind];
  const dev = item.deviation_days ?? 0;
  return (
    <button onClick={onClick} style={{ height: ROW }}
            className={`flex w-full items-center gap-2 border-b border-line/60 pl-9 pr-3 text-left transition hover:bg-elev ${active ? "bg-accent/[0.07]" : ""}`}>
      <Icon size={13} className="shrink-0 text-faint" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px]">{item.title}</span>
        <span className="hidden truncate text-[11px] text-faint sm:block">{item.id}{item.owner ? ` · ${item.owner}` : ""}</span>
      </span>
      {item.state === "late" && <span className="num shrink-0 text-[11px] font-semibold text-danger">{signed(dev)}</span>}
      {item.state === "done_late" && <span className="num shrink-0 text-[11px] font-medium text-warn">{signed(dev)}</span>}
      {(item.state === "at_risk" || item.state === "unconfirmed") && <AlertTriangle size={12} className="shrink-0 text-warn" />}
      {item.state === "done" && <CheckCircle2 size={12} className="shrink-0 text-success" />}
    </button>
  );
}

const grow = { initial: { scaleX: 0, opacity: 0 }, animate: { scaleX: 1, opacity: 1 } };
const ease = { duration: 0.7, ease: [0.16, 1, 0.3, 1] as const };

function ItemBars({ item, x, onClick }: { item: Item; x: (s: string) => number; onClick: () => void }) {
  const p = item.plan, f = item.forecast, b = item.baseline;
  const tip = `${item.id} · plan ${fmt(p.start)} → ${fmt(p.end)} · forecast ${fmt(f.end)} · ${lag(item.deviation_days)}`;
  if (item.milestone || !p.start) {
    if (!p.end) return null;
    const late = f.end && f.end > p.end;
    return (
      <button onClick={onClick} title={tip} className="absolute inset-0">
        {late && <>
          <motion.span className="absolute top-1/2 h-px origin-left border-t border-dashed border-danger/70" style={{ left: x(p.end), width: x(f.end!) - x(p.end) }}
                       {...grow} transition={{ ...ease, delay: 0.25 }} />
          <motion.span className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rotate-45 rounded-[3px] bg-danger shadow-[0_0_0_4px_color-mix(in_oklch,var(--danger)_18%,transparent)]"
                       style={{ left: x(f.end!) }} initial={{ opacity: 0, scale: 0.4 }} animate={{ opacity: 1, scale: 1 }} transition={{ ...ease, delay: 0.55 }} />
          <span className="num absolute top-1/2 -translate-y-1/2 pl-3 text-[11px] font-semibold text-danger" style={{ left: x(f.end!) }}>{signed(item.deviation_days ?? 0)}</span>
        </>}
        <motion.span className={`absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rotate-45 rounded-[3px] ${late ? "border border-ink-soft/70 bg-panel" : "bg-ink-soft/70"}`}
                     style={{ left: x(p.end) }} initial={{ opacity: 0, scale: 0.4 }} animate={{ opacity: 1, scale: 1 }} transition={ease} />
      </button>
    );
  }
  const done = item.state === "done" || item.state === "done_late";
  const shifted = !!(f.start && f.start > p.start);
  const overrun = !shifted && f.end && p.end && f.end > p.end;
  const baseMoved = b.start && b.end && (b.start !== p.start || b.end !== p.end);
  const planCls = done ? "bg-success/70" : item.state === "late" || item.state === "unconfirmed" ? "bg-ink-soft/35"
    : item.state === "at_risk" ? "bg-warn/75" : "bg-accent/80";
  const end = f.end && f.end > (p.end ?? "") ? f.end : p.end!;
  return (
    <button onClick={onClick} title={tip} className="group absolute inset-0">
      {baseMoved && <span className="absolute top-1/2 h-[18px] -translate-y-1/2 rounded-full border border-dashed border-ink-soft/50"
                          style={{ left: x(b.start!), width: Math.max(x(b.end!) - x(b.start!), 6) }} />}
      <motion.span className={`absolute top-1/2 h-3.5 origin-left -translate-y-1/2 rounded-full ${planCls} ${shifted ? "opacity-40" : ""} transition group-hover:brightness-110`}
                   style={{ left: x(p.start), width: Math.max(x(done && f.end ? f.end : p.end!) - x(p.start), 6) }} {...grow} transition={ease} />
      {overrun && !done && <motion.span className="gantt-overrun absolute top-1/2 h-3.5 origin-left -translate-y-1/2 rounded-r-full"
                                        style={{ left: x(p.end!) - 4, width: x(f.end!) - x(p.end!) + 4 }} {...grow} transition={{ ...ease, delay: 0.35 }} />}
      {overrun && done && <motion.span className="absolute top-1/2 h-3.5 origin-left -translate-y-1/2 rounded-r-full bg-warn/70"
                                       style={{ left: x(p.end!) - 4, width: x(f.end!) - x(p.end!) + 4 }} {...grow} transition={{ ...ease, delay: 0.35 }} />}
      {shifted && <>
        <motion.span className="absolute top-1/2 h-px origin-left border-t border-dashed border-danger/60"
                     style={{ left: x(p.end!), width: Math.max(x(f.start!) - x(p.end!), 0) }} {...grow} transition={{ ...ease, delay: 0.2 }} />
        <motion.span className="gantt-overrun absolute top-1/2 h-3.5 origin-left -translate-y-1/2 rounded-full"
                     style={{ left: x(f.start!), width: Math.max(x(f.end!) - x(f.start!), 6) }} {...grow} transition={{ ...ease, delay: 0.45 }} />
      </>}
      {(item.deviation_days ?? 0) > 0 && (
        <span className={`num absolute top-1/2 -translate-y-1/2 pl-2 text-[11px] font-semibold ${done ? "text-warn" : "text-danger"}`} style={{ left: x(end) }}>
          {signed(item.deviation_days!)}
        </span>
      )}
    </button>
  );
}

function GroupBar({ group, x }: { group: Group; x: (s: string) => number }) {
  const p = group.plan, f = group.forecast;
  if (!p.start || !p.end) return null;
  const late = f.end && f.end > p.end;
  return (
    <>
      <motion.span className="absolute top-1/2 h-2 origin-left -translate-y-1/2 rounded-full bg-ink-soft/45"
                   style={{ left: x(p.start), width: x(p.end) - x(p.start) }} {...grow} transition={ease} />
      <span className="absolute top-1/2 h-4 w-0.5 -translate-y-1/2 rounded bg-ink-soft/70" style={{ left: x(p.end) }} />
      {late && <>
        <motion.span className="gantt-overrun absolute top-1/2 h-2 origin-left -translate-y-1/2 rounded-r-full"
                     style={{ left: x(p.end), width: x(f.end!) - x(p.end) }} {...grow} transition={{ ...ease, delay: 0.3 }} />
        <span className="num absolute top-1/2 -translate-y-1/2 pl-2 text-[11px] font-semibold text-danger" style={{ left: x(f.end!) }}>
          target {signed(group.deviation_days ?? 0)}
        </span>
      </>}
    </>
  );
}

/** Lines from a late build to the customer orders waiting on it, with a slow flow along them. */
function Connectors({ rows, x }: { rows: Row[]; x: (s: string) => number }) {
  const at = new Map<string, number>();
  rows.forEach((r, n) => { if (r.item) at.set(`${r.group.id}/${r.item.id}`, n); });
  const paths: { d: string; key: string }[] = [];
  rows.forEach((r, n) => {
    const i = r.item;
    if (!i || i.kind !== "order" || !i.driver || !i.forecast.end) return;
    const from = at.get(`${r.group.id}/${i.driver}`);
    if (from === undefined) return;
    const src = rows[from].item!;
    if (!src.forecast.end) return;
    const x1 = x(src.forecast.end), y1 = from * ROW + ROW / 2, x2 = x(i.forecast.end), y2 = n * ROW + ROW / 2;
    const mid = Math.max(x1, x2) + 18;
    paths.push({ key: r.key, d: `M ${x1 + 2} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2 + 8} ${y2}` });
  });
  if (!paths.length) return null;
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible" aria-hidden>
      {paths.map((p) => (
        <g key={p.key}>
          <motion.path d={p.d} fill="none" stroke="var(--danger)" strokeOpacity={0.45} strokeWidth={1.25}
                       initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.9, delay: 0.6, ease: [0.16, 1, 0.3, 1] }} />
          <path d={p.d} fill="none" stroke="var(--danger)" strokeWidth={1.25} strokeDasharray="2 10" className="ripple-flow" strokeOpacity={0.8} />
        </g>
      ))}
    </svg>
  );
}

function Detail({ entry, all, onSelect, onClose }: { entry: Item | Group; all: Item[]; onSelect: (id: string) => void; onClose: () => void }) {
  const isItem = "kind" in entry;
  const Icon = isItem ? KIND[entry.kind] : Flag;
  const s = STATE[entry.state];
  const driver = entry.driver ? all.find((i) => i.id === entry.driver) : null;
  const waiting = isItem ? all.filter((i) => i.driver === entry.id) : [];
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <motion.aside initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }}
                  transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                  className="fixed bottom-3 right-3 top-3 z-40 flex w-[min(420px,calc(100vw-24px))] flex-col overflow-hidden rounded-2xl border border-line bg-panel shadow-2xl">
      <header className="flex items-start gap-3 border-b border-line p-4">
        <span className="mt-0.5 rounded-lg bg-elev p-2"><Icon size={16} className="text-muted" /></span>
        <div className="min-w-0 flex-1">
          <div className="font-mono text-[11.5px] text-muted">{entry.id}{isItem && entry.owner ? ` · ${entry.owner}` : ""}{!isItem && entry.lead ? ` · led by ${entry.lead}` : ""}</div>
          <div className="mt-0.5 text-[15px] font-semibold leading-snug tracking-tight">{isItem ? entry.title : entry.name}</div>
          <div className="mt-2 flex flex-wrap items-center gap-2"><Pill tone={s.tone} dot>{s.label}</Pill>
            <span className={`num text-[12.5px] font-medium ${(entry.deviation_days ?? 0) > 0 ? "text-danger" : "text-muted"}`}>{lag(entry.deviation_days)}</span></div>
        </div>
        <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-muted hover:bg-elev hover:text-ink"><X size={16} /></button>
      </header>
      <div className="flex-1 space-y-5 overflow-y-auto p-4 text-[13px]" data-lenis-prevent>
        <table className="num w-full text-left">
          <thead className="text-[11px] uppercase tracking-wider text-faint"><tr><th className="pb-1.5 font-medium" /><th className="pb-1.5 font-medium">Start</th><th className="pb-1.5 font-medium">Finish</th></tr></thead>
          <tbody className="[&_td]:py-1">
            <tr><td className="text-muted">Baseline</td><td>{fmt(entry.baseline.start)}</td><td>{fmt(entry.baseline.end)}</td></tr>
            <tr><td className="text-muted">Plan</td><td>{fmt(entry.plan.start)}</td><td>{fmt(entry.plan.end)}</td></tr>
            <tr className={(entry.deviation_days ?? 0) > 0 ? "text-danger" : ""}><td className="font-medium">Forecast</td><td>{fmt(entry.forecast.start)}</td><td className="font-semibold">{fmt(entry.forecast.end)}</td></tr>
          </tbody>
        </table>
        {entry.reasons.length > 0 && (
          <div>
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-faint">Why</div>
            <ul className="space-y-1.5">{entry.reasons.map((r) => <li key={r} className="flex gap-2"><span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ink-soft" />{r}</li>)}</ul>
          </div>
        )}
        {isItem && entry.penalty && (
          <div className="rounded-xl border border-danger/30 bg-danger/[0.06] p-3">
            <div className="text-[11px] font-medium uppercase tracking-wider text-danger">Penalty exposure</div>
            <div className="mt-1">
              {entry.deviation_days} days late is {entry.penalty.weeks_late} started weeks at {entry.penalty.per_week_pct}% a week
              {entry.penalty.capped ? `, capped at ${entry.penalty.pct}%` : `: ${entry.penalty.pct}%`} of the order, about <b>{inr(entry.penalty.value)}</b>.
            </div>
            {entry.penalty.note && <div className="mt-0.5 text-[12px] text-muted">{entry.penalty.note}</div>}
          </div>
        )}
        {driver && (
          <div>
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-faint">Held up by</div>
            <button onClick={() => onSelect(driver.id)} className="lift w-full rounded-xl border border-line bg-elev p-3 text-left hover:border-danger/40">
              <div className="flex items-center justify-between"><span className="font-mono text-[11.5px] text-muted">{driver.id}</span><span className="num text-[12px] font-semibold text-danger">{lag(driver.deviation_days)}</span></div>
              <div className="mt-0.5 text-[13px] font-medium">{driver.title}</div>
            </button>
          </div>
        )}
        {waiting.length > 0 && (
          <div>
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-faint">Waiting on this</div>
            <div className="space-y-1.5">{waiting.map((w) => (
              <button key={w.id} onClick={() => onSelect(w.id)} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-elev">
                {(() => { const I = KIND[w.kind]; return <I size={13} className="text-faint" />; })()}
                <span className="min-w-0 flex-1 truncate">{w.title}</span><span className="num text-[11.5px] text-danger">{signed(w.deviation_days ?? 0)}</span>
              </button>))}</div>
          </div>
        )}
        {!isItem && (
          <div>
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-faint">In this project</div>
            <div className="flex flex-wrap gap-1.5">{entry.items.map((i) => (
              <button key={i.id} onClick={() => onSelect(i.id)} className={`rounded-full border px-2 py-0.5 font-mono text-[11px] transition hover:border-line2 ${DEVIATED.includes(i.state) ? "border-danger/35 text-danger" : "border-line text-muted"}`}>{i.id}</button>))}</div>
          </div>
        )}
        <div className="flex items-center gap-2 text-[11.5px] text-faint"><CalendarRange size={12} /> Dates come from the system of record; the forecast is calculated by code.</div>
      </div>
    </motion.aside>
  );
}

