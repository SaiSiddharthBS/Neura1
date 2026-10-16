"use client";

import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import { api } from "@/lib/api";

type Item = { kind: string; at: string; who: string | null; what: string; detail: string; ref: string };
type Flag = { record: string; label: string; chunk: string | null; reason: string };

const KIND: Record<string, string> = { message: "bg-bg", decision: "bg-red-50 text-danger", investigation: "bg-teal-50 text-accent", quote: "bg-amber-50 text-warn" };

export default function Changes() {
  const [d, setD] = useState<{ feed: Item[]; attention: Flag[] } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { api<{ feed: Item[]; attention: Flag[] }>("/api/changes").then(setD); }, []);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">What&apos;s new</h1>
        <p className="mt-1 text-sm text-muted">Everything that reached the company graph, newest first.</p>
        <ol className="card mt-4 divide-y divide-line">
          {d?.feed.map((f, i) => (
            <li key={i} className="flex gap-3 p-3 text-sm">
              <span className="w-24 shrink-0 text-xs text-muted">{f.at.slice(0, 10)}</span>
              <span className={`h-fit shrink-0 rounded px-1.5 py-0.5 text-[11px] ${KIND[f.kind] ?? "bg-bg"}`}>{f.kind}</span>
              <button disabled={!f.ref.includes("#")} onClick={() => setOpen(f.ref)} className="min-w-0 flex-1 text-left enabled:hover:underline">
                <div className="font-medium">{f.what}{f.who ? <span className="font-normal text-muted"> · {f.who}</span> : null}</div>
                <div className="line-clamp-2 text-muted">{f.detail}</div>
              </button>
            </li>
          ))}
        </ol>
      </section>
      <aside className="card h-fit p-4">
        <div className="flex items-center gap-2 font-medium"><AlertTriangle size={16} className="text-warn" /> Needs attention</div>
        <p className="mt-1 text-xs text-muted">Knowledge that may no longer be true, found from the graph&apos;s structure.</p>
        <ul className="mt-3 space-y-2 text-sm">
          {d?.attention.map((a, i) => (
            <li key={i} className="rounded-lg border border-warn/30 bg-amber-50 p-2">
              <b className="font-mono text-xs">{a.record}</b> <span className="text-xs text-muted">{a.label}</span>
              <div>{a.reason}</div>
            </li>
          ))}
          {d && !d.attention.length && <li className="text-muted">Nothing stale right now.</li>}
        </ul>
      </aside>
      {open && <EvidenceDrawer key={open} chunk={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
