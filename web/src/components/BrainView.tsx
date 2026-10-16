"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import AskBox from "@/components/AskBox";
import WhoKnows from "@/components/WhoKnows";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import { api } from "@/lib/api";

type Overview = {
  labels: { label: string; n: number }[];
  relationships: { type: string; n: number }[];
  teams: { team: string; people: { name: string; role: string }[]; owns: string[] }[];
  sources: { id: string; kind: string; title: string; passages: number }[];
};
type Hit = { chunk: string; title: string; kind: string; text: string; author: string | null; page: number | null; score: number };

export default function BrainView() {
  const params = useSearchParams();
  const [o, setO] = useState<Overview | null>(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => { api<Overview>("/api/overview").then(setO); }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Company brain</h1>
        <p className="mt-1 text-sm text-muted">One FalkorDB graph of Voltline&apos;s records, documents, chats, tickets, people and decisions.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {o?.labels.map((l) => (
          <span key={l.label} className="rounded-lg border border-line bg-panel px-3 py-1.5 text-sm">
            <b>{l.n}</b> <span className="text-muted">{l.label}</span>
          </span>
        ))}
        {o && <span className="rounded-lg border border-line bg-panel px-3 py-1.5 text-sm">
          <b>{o.relationships.reduce((s, r) => s + r.n, 0)}</b> <span className="text-muted">relationships</span>
        </span>}
      </div>

      <AskBox key={params.get("ask") ?? ""} onOpen={setOpen} initial={params.get("ask") ?? undefined} />
      <WhoKnows key={params.get("who") ?? ""} onOpen={setOpen} initial={params.get("who") ?? undefined} />

      <section className="card p-4">
        <form onSubmit={(e) => { e.preventDefault(); api<Hit[]>(`/api/search?q=${encodeURIComponent(q)}`).then(setHits); }}
              className="flex gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search everything Voltline has written, e.g. thermal"
                 className="flex-1 rounded-md border border-line px-3 py-2 text-sm" />
          <button className="rounded-md bg-accent px-4 text-sm text-white">Search</button>
        </form>
        {hits && (
          <ul className="mt-3 divide-y divide-line">
            {hits.length === 0 && <li className="py-2 text-sm text-muted">No passages match.</li>}
            {hits.map((h) => (
              <li key={h.chunk} className="cursor-pointer py-2 text-sm hover:bg-bg" onClick={() => setOpen(h.chunk)}>
                <div className="text-xs text-muted">{h.kind} · {h.title}{h.author ? ` · ${h.author}` : ""}{h.page ? ` · p.${h.page}` : ""}</div>
                <div className="line-clamp-2">{h.text}</div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card p-4">
          <h2 className="font-medium">People and what they own</h2>
          <div className="mt-3 space-y-3 text-sm">
            {o?.teams.map((t) => (
              <div key={t.team}>
                <div className="text-xs uppercase tracking-wide text-muted">{t.team}</div>
                {t.people.map((p) => <div key={p.name}>{p.name} <span className="text-muted">· {p.role}</span></div>)}
                {t.owns.filter(Boolean).length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {t.owns.filter(Boolean).map((x) => <span key={x} className="rounded bg-bg px-1.5 py-0.5 font-mono text-xs">{x}</span>)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
        <section className="card p-4">
          <h2 className="font-medium">Knowledge sources</h2>
          <ul className="mt-3 divide-y divide-line text-sm">
            {o?.sources.map((s) => (
              <li key={s.id} className="flex justify-between gap-3 py-2">
                <span><span className="mr-2 rounded bg-bg px-1.5 py-0.5 text-xs text-muted">{s.kind}</span>{s.title}</span>
                <span className="shrink-0 text-xs text-muted">{s.passages} passages</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
      {open && <EvidenceDrawer key={open} chunk={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
