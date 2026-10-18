"use client";

import Link from "next/link";
import { ArrowUpRight, Bot, Database, GanttChartSquare } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Gantt = {
  summary: { late: number; projects_late: number; at_risk: number; items: number;
             worst: { id: string; title: string; deviation_days: number }[] };
  groups: { id: string; name: string; deviation_days: number | null; forecast: { end: string | null } }[];
};
type Connect = { source: { simulated: boolean }; runs: { at: string; changes: number }[] };
type Agents = { mcp: { enabled: boolean }; sharing: { enabled: boolean } };

const lag = (d: number) => (d >= 14 ? `${Math.round(d / 7)} weeks late` : `${d} days late`);
const ago = (iso: string) => {
  const m = Math.max(0, Math.round((new Date().getTime() - new Date(iso).getTime()) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
};

/** The plan's health and the systems Neura1 works with, at the top of the overview. */
export default function PlanStrip() {
  const [g, setG] = useState<Gantt | null>(null);
  const [c, setC] = useState<Connect | null>(null);
  const [a, setA] = useState<Agents | null>(null);
  useEffect(() => {
    api<Gantt>("/api/gantt").then(setG).catch(() => {});
    api<Connect>("/api/connect").then(setC).catch(() => {});
    api<Agents>("/api/agents").then(setA).catch(() => {});
  }, []);
  const late = g?.groups.filter((x) => (x.deviation_days ?? 0) > 0) ?? [];
  const last = c?.runs[0];

  return (
    <div className="grid gap-3 lg:grid-cols-[1.7fr_1fr]">
      <Link href="/timeline" className="card lift group flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <div className="flex items-center gap-3 sm:w-[280px] sm:shrink-0">
          <span className="rounded-xl bg-danger/12 p-2.5 text-danger"><GanttChartSquare size={18} /></span>
          <div>
            <div className="text-[12px] font-medium uppercase tracking-wider text-faint">Plan health</div>
            <div className="text-[15px] font-semibold tracking-tight">
              {g ? <><span className="num text-danger">{g.summary.late}</span> late · <span className="num">{g.summary.projects_late}</span> project{g.summary.projects_late === 1 ? "" : "s"} past target</> : "Reading the plan…"}
            </div>
          </div>
        </div>
        <div className="min-w-0 flex-1 space-y-1 text-[12.5px]">
          {late.slice(0, 1).map((p) => (
            <div key={p.id} className="truncate"><span className="text-muted">Project</span> {p.name} <span className="num font-medium text-danger">+{p.deviation_days} days</span></div>
          ))}
          {g?.summary.worst.slice(0, 2).map((w) => (
            <div key={w.id} className="truncate"><span className="font-mono text-[11.5px] text-muted">{w.id}</span> {w.title.replace(`Build ${w.id}: `, "").replace(`${w.id}: `, "")} <span className="num font-medium text-danger">{lag(w.deviation_days)}</span></div>
          ))}
        </div>
        <span className="flex shrink-0 items-center gap-1 text-[12.5px] text-muted transition group-hover:text-ink">Open the timeline <ArrowUpRight size={13} /></span>
      </Link>
      <Link href="/connect" className="card lift group flex flex-col justify-center gap-2 p-4">
        <div className="flex items-center justify-between">
          <div className="text-[12px] font-medium uppercase tracking-wider text-faint">Works with</div>
          <ArrowUpRight size={13} className="text-muted transition group-hover:text-ink" />
        </div>
        <div className="flex items-center gap-2 text-[13px]">
          <Database size={14} className="shrink-0 text-accent" />
          <span className="font-medium">Zoho</span>
          <span className="truncate text-muted">
            {c ? (last ? `synced ${ago(last.at)}, ${last.changes} change${last.changes === 1 ? "" : "s"}` : "over MCP · ready to sync") : "…"}
            {c?.source.simulated ? " (simulated)" : ""}
          </span>
        </div>
        <div className="flex items-center gap-2 text-[13px]">
          <Bot size={14} className="shrink-0 text-violet" />
          <span className="font-medium">OpenAI Dots</span>
          <span className="text-muted">{a ? (a.mcp.enabled ? "on: answers agents when they ask" : "optional · off, nothing leaves") : "…"}</span>
        </div>
      </Link>
    </div>
  );
}
