"use client";

import Link from "next/link";
import { Activity, Brain, Building2, Network, PackageX, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { api, inr } from "@/lib/api";

type Risk = {
  chokepoints: { id: string; label: string; name: string; score: number }[];
  single_source: { id: string; name: string; revisions: string[]; orders: string[]; value_at_risk: number }[];
  no_quote: { id: string; name: string; value_at_risk: number }[];
  bus_factor: { id: string; label: string; person: string; person_id: string; share: number; away: string[] }[];
  concentration: { customer: string; value: number; share: number }[];
  load: { id: string; name: string; open_tasks: number; upcoming_absence: string[] }[];
  communities: { members: string[]; people: string[]; teams: string[]; crosses_teams: boolean }[];
  trace: { name: string; cypher: string; ms: number }[];
};

const LINK: Record<string, (id: string) => string> = {
  Person: (id) => `/people?id=${id}`, Project: (id) => `/projects?id=${id}`, Customer: (id) => `/customers?id=${id}`,
};

export default function RiskRadar() {
  const [r, setR] = useState<Risk | null>(null);
  useEffect(() => { api<Risk>("/api/risk").then(setR); }, []);
  if (!r) return <div className="p-6 text-muted">Running graph algorithms on the company…</div>;
  const maxScore = Math.max(...r.chokepoints.map((c) => c.score), 1);
  const algoMs = r.trace.reduce((s, t) => s + t.ms, 0);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="page-title">Risk radar</h1>
        <p className="mt-1 text-sm text-muted">
          Where Flyvi is fragile, found by FalkorDB graph algorithms and traversals across people, products, customers and suppliers.
          {" "}{r.trace.length} queries, {algoMs.toFixed(0)} ms.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel icon={Network} title="Structural chokepoints" note="Betweenness centrality: the records most other connections pass through. Disrupt one of these and most of the company feels it.">
          {r.chokepoints.map((c) => (
            <div key={c.id} className="flex items-center gap-3 py-1 text-sm">
              <span className="w-40 truncate">{LINK[c.label] ? <Link className="hover:underline" href={LINK[c.label](c.id)}>{c.name}</Link> : c.name}<span className="ml-1 text-xs text-muted">{c.label}</span></span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-elev"><div className="h-full rounded-full bg-gradient-to-r from-accent to-cyan" style={{ width: `${(100 * c.score) / maxScore}%` }} /></div>
              <span className="w-12 text-right font-mono text-xs text-muted tabular-nums">{c.score.toFixed(0)}</span>
            </div>
          ))}
        </Panel>

        <Panel icon={PackageX} title="Supply: single source" note="Parts in released products with one supplier on a valid quote, and the open order value that depends on them.">
          {r.single_source.map((s) => (
            <div key={s.id} className="rounded-xl border border-danger/25 bg-danger/[0.07] p-3 text-sm">
              <div className="flex justify-between gap-2"><Link href={`/impact?item=${s.id}`} className="font-mono font-medium hover:underline">{s.id}</Link><span className="text-danger tabular-nums">{inr(s.value_at_risk)} at risk</span></div>
              <div className="text-xs text-muted">{s.name} · in {s.revisions.join(", ")} · orders {s.orders.join(", ")}</div>
            </div>
          ))}
          {r.no_quote.length > 0 && <div className="mt-2 text-xs text-muted">No quote on file at all: {r.no_quote.map((n) => n.id).join(", ")}. Their prices and lead times are unknown.</div>}
        </Panel>

        <Panel icon={Brain} title="Knowledge held by one person" note="Subjects where one person carries most of what the company knows (ownership, decisions, what they wrote). Flagged red if they have leave coming up.">
          {r.bus_factor.map((b) => (
            <div key={b.id} className={`flex items-center gap-3 rounded-lg px-2 py-1.5 text-sm ${b.away.length ? "bg-warn/10" : ""}`}>
              <span className="w-28 truncate font-mono text-xs">{b.id}</span>
              <Link href={`/people?id=${b.person_id}`} className="flex-1 hover:underline">{b.person}</Link>
              <span className="text-xs text-muted tabular-nums">{Math.round(b.share * 100)}%</span>
              {b.away.length > 0 && <span className="text-xs text-warn">away {b.away[0]}</span>}
            </div>
          ))}
        </Panel>

        <Panel icon={Building2} title="Customer concentration" note="Share of open order value per customer.">
          {r.concentration.map((c) => (
            <div key={c.customer} className="flex items-center gap-3 py-1 text-sm">
              <Link href={`/customers?id=${c.customer}`} className="w-28 font-mono text-xs hover:underline">{c.customer}</Link>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-elev"><div className="h-full rounded-full bg-violet" style={{ width: `${c.share * 100}%` }} /></div>
              <span className="w-28 text-right text-xs text-muted tabular-nums">{inr(c.value)} · {Math.round(c.share * 100)}%</span>
            </div>
          ))}
        </Panel>

        <Panel icon={Users} title="How work actually clusters" note="Community detection (label propagation) on who owns, leads and works on what. Clusters that cross team lines show how the company really works, beyond the org chart.">
          {r.communities.map((c, i) => (
            <div key={i} className="rounded-xl border border-line bg-elev p-3 text-sm">
              <div className="font-medium">{c.people.join(", ")}</div>
              <div className="mt-1 text-xs text-muted">{c.teams.join(" · ")}{c.crosses_teams ? " · crosses teams" : ""}</div>
              <div className="mt-1 font-mono text-[11px] text-muted">{c.members.filter((m) => !m.startsWith("P-")).join(" · ")}</div>
            </div>
          ))}
        </Panel>

        <Panel icon={Activity} title="Workload and leave" note="Open tasks per person, and leave that overlaps them.">
          {r.load.map((p) => (
            <div key={p.id} className="flex items-center gap-3 py-1 text-sm">
              <Link href={`/people?id=${p.id}`} className="w-36 hover:underline">{p.name}</Link>
              <div className="flex flex-1 gap-1">{Array.from({ length: p.open_tasks }).map((_, i) => <span key={i} className="h-3 w-3 rounded-sm bg-accent/70" />)}</div>
              {p.upcoming_absence.length > 0 && <span className="text-xs text-warn">away {p.upcoming_absence[0]}</span>}
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}

function Panel({ icon: Icon, title, note, children }: { icon: React.ElementType; title: string; note: string; children: React.ReactNode }) {
  return (
    <section className="card p-4">
      <div className="flex items-center gap-2 font-medium"><Icon size={16} className="text-accent-hover" /> {title}</div>
      <p className="mb-3 mt-1 text-xs text-muted">{note}</p>
      <div className="space-y-2">{children}</div>
    </section>
  );
}
