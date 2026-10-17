"use client";

import Link from "next/link";
import { Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type Signal = { signal: string; evidence: string; ts: string | null };
type Person = { id: string; name: string; role: string; team: string; score: number; signals: Signal[] };
type Result = {
  subject: { id: string; label: string; name: string } | null;
  people: Person[];
  candidates?: { id: string; label: string; name: string }[];
  by_text?: { name: string; passages: number }[];
};

const EXAMPLES = ["NB54360", "pmic_seq.c", "Nilgiri", "PDU-48", "PSM-28"];

export default function WhoKnows({ onOpen, initial }: { onOpen?: (chunk: string) => void; initial?: string }) {
  const [q, setQ] = useState("");
  const [r, setR] = useState<Result | null>(null);

  const started = useRef(false);
  useEffect(() => {
    if (initial && !started.current) { started.current = true; run(initial); }
  }, [initial]);

  async function run(text: string) {
    setQ(text);
    setR(await api<Result>(`/api/brain/who-knows?q=${encodeURIComponent(text)}`));
  }

  return (
    <section className="card p-4">
      <div className="flex items-center gap-2 font-medium"><Users size={16} className="text-accent" /> Who knows about…</div>
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) run(q.trim()); }} className="mt-3 flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="A part, project, customer, or a name people use in chat"
               className="flex-1 rounded-md border border-line px-3 py-2 text-sm" />
        <button className="rounded-md bg-accent px-4 text-sm text-white">Find</button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((x) => (
          <button key={x} onClick={() => run(x)} className="rounded-full border border-line px-2.5 py-0.5 font-mono text-xs text-muted hover:border-ink hover:text-ink">{x}</button>
        ))}
      </div>
      {r && !r.subject && (
        <p className="mt-3 text-sm text-muted">
          Nothing in the graph is called “{q}”.
          {r.by_text?.length ? <> People who wrote about it: {r.by_text.map((b) => `${b.name} (${b.passages})`).join(", ")}.</> : null}
        </p>
      )}
      {r?.subject && (
        <div className="mt-4">
          <div className="text-xs uppercase tracking-wide text-muted">{r.subject.label} · {r.subject.id} · {r.subject.name}</div>
          <ol className="mt-2 divide-y divide-line">
            {r.people.map((p, i) => (
              <li key={p.id} className="flex flex-wrap items-start gap-x-4 gap-y-1 py-2 text-sm">
                <span className="w-5 text-muted">{i + 1}</span>
                <Link href={`/people?id=${p.id}`} className="w-44 font-medium hover:underline">{p.name}
                  <div className="text-xs font-normal text-muted">{p.role}</div></Link>
                <div className="flex flex-1 flex-wrap gap-1">
                  {p.signals.map((s, k) => (
                    s.evidence.includes("#") && onOpen
                      ? <button key={k} onClick={() => onOpen(s.evidence)} className="rounded bg-bg px-1.5 py-0.5 text-xs hover:underline">{s.signal} ↗</button>
                      : <span key={k} className="rounded bg-bg px-1.5 py-0.5 text-xs">{s.signal}{s.evidence !== r.subject!.id ? ` · ${s.evidence}` : ""}</span>
                  ))}
                </div>
              </li>
            ))}
          </ol>
          {r.people.length === 0 && <p className="text-sm text-muted">Nobody is recorded as owning, deciding or discussing this.</p>}
        </div>
      )}
    </section>
  );
}
