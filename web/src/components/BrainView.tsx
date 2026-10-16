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
type Hit = { chunk: string; title: string; kind: string; text: string; author: string | null; page: number | null; score: number;
             mentions: { id: string; label: string }[] };
type Search = { modes: string[]; hits: Hit[]; related: { id: string; label: string; passages: number }[] };

export default function BrainView() {
  const params = useSearchParams();
  const [o, setO] = useState<Overview | null>(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Search | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => { api<Overview>("/api/overview").then(setO); }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">Ask &amp; search</h1>
          <p className="mt-1.5 text-[15px] text-muted">Ask in plain language. Neura1 answers from one FalkorDB graph of Flyvi&apos;s records, documents, chats and decisions, and shows its sources.</p>
        </div>
        {o && (
          <div className="flex items-center gap-4 text-[12.5px] text-muted">
            {[
              [o.labels.reduce((s, l) => s + l.n, 0), "records"],
              [o.relationships.reduce((s, r) => s + r.n, 0), "links"],
              [o.labels.find((l) => l.label === "Chunk")?.n ?? 0, "passages"],
              [o.labels.find((l) => l.label === "Person")?.n ?? 0, "people"],
            ].map(([n, l]) => (
              <span key={l as string}><span className="num font-semibold text-ink">{n as number}</span> {l as string}</span>
            ))}
          </div>
        )}
      </div>

      <AskBox key={`ask:${params.get("ask") ?? ""}`} onOpen={setOpen} initial={params.get("ask") ?? undefined} />
      <WhoKnows key={`who:${params.get("who") ?? ""}`} onOpen={setOpen} initial={params.get("who") ?? undefined} />

      <section className="card p-4">
        <form onSubmit={(e) => { e.preventDefault(); api<Search>(`/api/search?q=${encodeURIComponent(q)}`).then(setHits); }}
              className="flex gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search everything Flyvi has written, by meaning or words, e.g. units losing power when cold"
                 className="flex-1 rounded-md border border-line px-3 py-2 text-sm" />
          <button className="rounded-md bg-accent px-4 text-sm text-white">Search</button>
        </form>
        {hits && (
          <div className="mt-3">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <span>Matched by {hits.modes.join(" + ") || "nothing"}{!hits.modes.includes("semantic") ? " (semantic search needs an embedding model)" : ""}.</span>
              {hits.related.length > 0 && <span>Related records:</span>}
              {hits.related.map((r) => <span key={r.id} className="rounded-md bg-elev px-1.5 py-0.5 font-mono text-[11px] text-ink">{r.id}</span>)}
            </div>
            <ul className="mt-2 divide-y divide-line">
              {hits.hits.length === 0 && <li className="py-2 text-sm text-muted">No passages match.</li>}
              {hits.hits.map((h) => (
                <li key={h.chunk} className="cursor-pointer py-2 text-sm hover:bg-elev" onClick={() => setOpen(h.chunk)}>
                  <div className="text-xs text-muted">{h.kind} · {h.title}{h.author ? ` · ${h.author}` : ""}{h.page ? ` · p.${h.page}` : ""}</div>
                  <div className="line-clamp-2">{h.text}</div>
                </li>
              ))}
            </ul>
          </div>
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
