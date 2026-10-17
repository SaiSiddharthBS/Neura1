"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { PageTitle } from "@/components/ui";
import { Avatar } from "@/components/ViewerSwitch";
import { api } from "@/lib/api";

type Person = { id: string; name: string; role: string; team: string; team_id: string; open_work: number; away_now: boolean };
type Org = {
  organizations: { id: string; name: string; kind: string; note: string; parent_id: string | null }[];
  people: Person[];
};

// The order the founders asked for: the three directors as peers, the leadership team under them, then everyone else.
const DIRECTORS = ["P-SURESH", "P-SATHISH", "P-JAYARAM"];
const LEADERSHIP = ["P-ANIL", "P-MARKANDE", "P-HITHESH", "P-PRAVEEN"];

function byOrder(people: Person[], order: string[]) {
  return [...people].sort((a, b) => (order.indexOf(a.id) + 1 || 99) - (order.indexOf(b.id) + 1 || 99) || a.name.localeCompare(b.name));
}

function PersonCard({ p, lead }: { p: Person; lead?: boolean }) {
  return (
    <Link href={`/people?id=${p.id}`}
          className={`group flex min-w-0 items-center gap-3 rounded-xl border px-3 py-2.5 transition hover:-translate-y-0.5 hover:border-line2 ${p.away_now ? "border-warn/30 bg-warn/[0.06]" : lead ? "border-accent/30 bg-accent/[0.07]" : "border-line bg-panel"}`}>
      <Avatar name={p.name} size={lead ? 36 : 30} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 truncate text-[13.5px] font-medium">{p.name}
          {p.away_now && <span className="rounded bg-warn/20 px-1 text-[9.5px] font-normal text-warn">away</span>}</span>
        <span className="block truncate text-[11.5px] text-muted">{p.role}{p.open_work ? ` · ${p.open_work} open` : ""}</span>
      </span>
    </Link>
  );
}

function Tier({ label, count, children, cols }: { label: string; count: number; children: React.ReactNode; cols: string }) {
  return (
    <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
                    className="relative">
      <div className="mb-2 flex items-baseline gap-2 px-1">
        <h2 className="text-[13px] font-semibold tracking-tight">{label}</h2>
        <span className="num text-[11.5px] text-muted">{count}</span>
      </div>
      <div className={`grid gap-2.5 ${cols}`}>{children}</div>
    </motion.section>
  );
}

function Connector() {
  return <div aria-hidden className="mx-auto h-7 w-px bg-gradient-to-b from-line2 to-transparent" />;
}

export default function OrgChart() {
  const [o, setO] = useState<Org | null>(null);
  useEffect(() => { api<Org>("/api/org").then(setO).catch(() => {}); }, []);

  const directors = o ? byOrder(o.people.filter((p) => p.team_id === "T-DIR"), DIRECTORS) : [];
  const leadership = o ? byOrder(o.people.filter((p) => p.team_id === "T-LEAD"), LEADERSHIP) : [];
  const employees = o ? byOrder(o.people.filter((p) => p.team_id !== "T-DIR" && p.team_id !== "T-LEAD"), []) : [];
  const parent = o?.organizations.find((x) => !x.parent_id);
  const flyvi = o?.organizations.find((x) => x.parent_id);

  return (
    <div className="space-y-5">
      <div>
        <PageTitle>How Flyvi is <em>organised</em></PageTitle>
        <p className="mt-1 text-sm text-muted">The directors, the leadership team under them, and everyone at Flyvi. Open work and who is away today are live from the graph. Click anyone for their profile.</p>
      </div>
      {o && (
        <div className="card space-y-1 p-5">
          {parent && flyvi && (
            <div className="mx-auto flex max-w-xl flex-wrap items-center justify-center gap-2 text-center text-[12.5px]">
              <span className="rounded-full border border-violet/40 bg-violet/10 px-3 py-1">{parent.name} <span className="text-muted">· {parent.kind}</span></span>
              <span className="text-faint">→</span>
              <span className="rounded-full border border-violet/40 bg-violet/10 px-3 py-1 font-medium">{flyvi.name}</span>
            </div>
          )}
          <Connector />
          <Tier label="Directors" count={directors.length} cols="sm:grid-cols-3">
            {directors.map((p) => <PersonCard key={p.id} p={p} lead />)}
          </Tier>
          <Connector />
          <Tier label="Leadership" count={leadership.length} cols="sm:grid-cols-2 lg:grid-cols-4">
            {leadership.map((p) => <PersonCard key={p.id} p={p} lead />)}
          </Tier>
          <Connector />
          <Tier label="Employees" count={employees.length} cols="grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
            {employees.map((p) => <PersonCard key={p.id} p={p} />)}
          </Tier>
        </div>
      )}
    </div>
  );
}
