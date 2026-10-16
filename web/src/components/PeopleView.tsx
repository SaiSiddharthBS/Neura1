"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import { api } from "@/lib/api";

type Row = { id: string; name: string; role: string; team: string; owns: number; projects: string[] };
type Profile = {
  id: string; name: string; role: string; team: string; backed_up_by: string[]; backs_up: string[];
  owns: { id: string; label: string; name: string }[];
  projects: { id: string; name: string; status: string; roles: string[] }[];
  decisions: { id: string; outcome: string; subject: string; summary: string; decided_at: string }[];
  tasks: { id: string; title: string; status: string; created_at: string }[];
  topics: { id: string; label: string; mentions: number; last: string }[];
  recent: { chunk: string; text: string; ts: string; title: string }[];
};

export default function PeopleView() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const [people, setPeople] = useState<Row[]>([]);
  const [p, setP] = useState<Profile | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => { api<Row[]>("/api/people").then(setPeople); }, []);
  useEffect(() => {
    if (id) api<Profile>(`/api/people/${id}`).then(setP);
  }, [id]);

  return (
    <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
      <aside className="card h-fit">
        <div className="border-b border-line p-4 font-medium">People</div>
        <ul className="divide-y divide-line text-sm">
          {people.map((r) => (
            <li key={r.id}>
              <button onClick={() => router.replace(`/people?id=${r.id}`)}
                      className={`w-full px-4 py-2 text-left hover:bg-bg ${r.id === id ? "bg-bg" : ""}`}>
                <div className="font-medium">{r.name}</div>
                <div className="text-xs text-muted">{r.role} · {r.team}</div>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {!id || !p ? (
        <div className="card p-6 text-sm text-muted">Pick a person to see what they own, what they know, and what they are working on.</div>
      ) : (
        <section className="space-y-4">
          <div className="card p-5">
            <h1 className="text-2xl font-semibold tracking-tight">{p.name}</h1>
            <div className="text-sm text-muted">{p.role} · {p.team}</div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              {p.backed_up_by.length > 0 && <span className="rounded-full bg-bg px-2 py-0.5">When away, ask {p.backed_up_by.join(", ")}</span>}
              {p.backs_up.length > 0 && <span className="rounded-full bg-bg px-2 py-0.5">Covers for {p.backs_up.join(", ")}</span>}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Card title="Owns">
              {p.owns.map((o) => <Chip key={o.id}>{o.id}<span className="text-muted"> · {o.label}</span></Chip>)}
              {!p.owns.length && <Empty />}
            </Card>
            <Card title="Knows about (from what they wrote)">
              {p.topics.map((t) => <Chip key={t.id}>{t.id}<span className="text-muted"> · {t.mentions}×</span></Chip>)}
              {!p.topics.length && <Empty />}
            </Card>
            <Card title="Projects">
              {p.projects.map((x) => (
                <Link key={x.id} href={`/projects?id=${x.id}`} className="block rounded-md px-2 py-1 text-sm hover:bg-bg">
                  {x.name} <span className="text-xs text-muted">· {x.roles.join(", ")} · {x.status}</span>
                </Link>
              ))}
              {!p.projects.length && <Empty />}
            </Card>
            <Card title="Decisions made">
              {p.decisions.map((d) => (
                <div key={d.id} className="text-sm"><b>{d.id}</b> {d.outcome} {d.subject} <span className="text-xs text-muted">· {d.decided_at}</span></div>
              ))}
              {!p.decisions.length && <Empty />}
            </Card>
          </div>
          <Card title={`Open tasks (${p.tasks.length})`}>
            {p.tasks.map((t) => <div key={t.id} className="text-sm">{t.title} <span className="text-xs text-muted">· {t.status}</span></div>)}
            {!p.tasks.length && <Empty />}
          </Card>
          <Card title="Recently said">
            {p.recent.map((r) => (
              <button key={r.chunk} onClick={() => setOpen(r.chunk)} className="block w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-bg">
                <span className="text-xs text-muted">{r.title} · {r.ts?.slice(0, 10)}</span>
                <div className="line-clamp-2">{r.text}</div>
              </button>
            ))}
            {!p.recent.length && <Empty />}
          </Card>
        </section>
      )}
      {open && <EvidenceDrawer key={open} chunk={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="card p-4"><div className="mb-2 text-xs uppercase tracking-wide text-muted">{title}</div><div className="flex flex-wrap gap-1.5">{children}</div></div>;
}
function Chip({ children }: { children: React.ReactNode }) {
  return <span className="rounded-md bg-bg px-2 py-0.5 font-mono text-xs">{children}</span>;
}
function Empty() {
  return <span className="text-sm text-muted">Nothing recorded.</span>;
}
