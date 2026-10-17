"use client";

import { PageTitle } from "@/components/ui";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import { api } from "@/lib/api";

type Row = { id: string; name: string; status: string; target_date: string; summary: string; lead: string; members: number; scope: string[] };
type Detail = {
  id: string; name: string; status: string; start_date: string; target_date: string; summary: string; lead: string; lead_id: string;
  members: { id: string; name: string; role: string; team: string }[];
  scope: { id: string; label: string; name: string }[];
  decisions: { id: string; outcome: string; subject: string; summary: string; decided_at: string; decided_by: string }[];
  tasks: { id: string; title: string; status: string; owner: string; via: string }[];
  activity: { chunk: string; text: string; author: string; ts: string; title: string }[];
};

const STATUS: Record<string, string> = { active: "bg-accent/12 text-accent", design: "bg-violet/12 text-violet", done: "bg-bg text-muted" };

export default function ProjectsView() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const [rows, setRows] = useState<Row[]>([]);
  const [d, setD] = useState<Detail | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => { api<Row[]>("/api/projects").then(setRows); }, []);
  useEffect(() => { if (id) api<Detail>(`/api/projects/${id}`).then(setD); }, [id]);

  return (
    <div className="space-y-6">
      <div>
        <PageTitle>Projects <em>in flight</em></PageTitle>
        <p className="mt-1 text-sm text-muted">Who is on them, what they cover, the decisions that touch them, and open work.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {rows.map((r) => (
          <button key={r.id} onClick={() => router.replace(`/projects?id=${r.id}`)}
                  className={`card p-4 text-left hover:border-ink ${r.id === id ? "border-ink" : ""}`}>
            <div className="flex items-start justify-between gap-2">
              <span className="font-medium leading-snug">{r.name}</span>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${STATUS[r.status] ?? "bg-bg"}`}>{r.status}</span>
            </div>
            <div className="mt-1 text-xs text-muted">Lead {r.lead} · {r.members} people · target {r.target_date}</div>
            <div className="mt-2 line-clamp-2 text-sm text-muted">{r.summary}</div>
          </button>
        ))}
      </div>

      {d && (
        <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          <div className="card space-y-4 p-5 lg:col-span-2">
            <div>
              <div className="text-xs uppercase tracking-wide text-muted">{d.id} · {d.start_date} → {d.target_date}</div>
              <h2 className="mt-1 text-xl font-semibold">{d.name}</h2>
              <p className="mt-1 text-sm text-muted">{d.summary}</p>
            </div>
            <div className="flex flex-wrap gap-2 text-sm">
              {d.members.map((m) => (
                <Link key={m.id} href={`/people?id=${m.id}`} className="rounded-full border border-line px-3 py-1 hover:border-ink">
                  {m.name} <span className="text-xs text-muted">· {m.role}</span>
                </Link>
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {d.scope.map((s) => <span key={s.id} className="rounded-md bg-bg px-2 py-0.5 font-mono text-xs">{s.id} <span className="text-muted">· {s.label}</span></span>)}
            </div>
          </div>
          <div className="card p-4">
            <div className="mb-2 text-xs uppercase tracking-wide text-muted">Decisions touching this project</div>
            {d.decisions.map((x) => (
              <div key={x.id} className="py-1 text-sm"><b>{x.id}</b> {x.outcome} {x.subject} · {x.decided_by} <span className="text-xs text-muted">· {x.decided_at}</span>
                <div className="text-xs text-muted">{x.summary}</div></div>
            ))}
            {!d.decisions.length && <p className="text-sm text-muted">None recorded.</p>}
          </div>
          <div className="card p-4">
            <div className="mb-2 text-xs uppercase tracking-wide text-muted">Open tasks in scope</div>
            {d.tasks.map((t) => <div key={t.id} className="py-1 text-sm">{t.title} <span className="text-xs text-muted">· {t.owner} · via {t.via}</span></div>)}
            {!d.tasks.length && <p className="text-sm text-muted">No open tasks. Approve an impact investigation and its tasks appear here.</p>}
          </div>
          <div className="card p-4 lg:col-span-2">
            <div className="mb-2 text-xs uppercase tracking-wide text-muted">Recent discussion</div>
            {d.activity.map((a) => (
              <button key={a.chunk} onClick={() => setOpen(a.chunk)} className="block w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-bg">
                <span className="text-xs text-muted">{a.title}{a.author ? ` · ${a.author}` : ""} · {a.ts?.slice(0, 10)}</span>
                <div className="line-clamp-2">{a.text}</div>
              </button>
            ))}
          </div>
        </section>
      )}
      {open && <EvidenceDrawer key={open} chunk={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
