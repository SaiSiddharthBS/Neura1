"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Passage = {
  id: string; text: string; author: string | null; ts: string | null; page: number | null;
  source: string; title: string; kind: string; mentions: string[]; stale: boolean;
  context: { id: string; text: string; author: string | null; ts: string | null; page: number | null }[];
};

function Highlight({ text, quote }: { text: string; quote?: string }) {
  const i = quote ? text.indexOf(quote) : -1;
  if (!quote || i < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded bg-amber-200 px-0.5">{quote}</mark>
      {text.slice(i + quote.length)}
    </>
  );
}

export default function EvidenceDrawer({ chunk, quote, onClose }: { chunk: string; quote?: string; onClose: () => void }) {
  const [p, setP] = useState<Passage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Passage>(`/api/evidence?chunk_id=${encodeURIComponent(chunk)}`).then(setP).catch((e) => setError(e.message));
  }, [chunk]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/20" onClick={onClose}>
      <aside className="h-full w-full max-w-xl overflow-y-auto bg-panel p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-wide text-muted">Source {p ? `· ${p.kind}` : ""}</div>
            <h2 className="mt-0.5 font-semibold">{p?.title ?? "Loading…"}</h2>
            {p && <div className="mt-1 font-mono text-xs text-muted">{p.source}</div>}
          </div>
          <button onClick={onClose} className="rounded p-1 hover:bg-bg" aria-label="Close"><X size={18} /></button>
        </div>
        {error && <p className="mt-4 text-sm text-danger">{error}</p>}
        {p?.stale && (
          <p className="mt-3 rounded-md bg-amber-50 p-2 text-xs text-warn">
            This source has changed since this passage was linked. Re-check before relying on it.
          </p>
        )}
        {p && (
          <div className="mt-4 space-y-2">
            {p.context.map((c) => (
              <div key={c.id}
                   className={`rounded-lg border p-3 text-sm ${c.id === p.id ? "border-ink bg-white shadow-sm" : "border-line bg-bg text-muted"}`}>
                {(c.author || c.ts || c.page) && (
                  <div className="mb-1 text-xs text-muted">
                    {[c.author, c.ts?.replace("T", " ").slice(0, 16), c.page ? `page ${c.page}` : null].filter(Boolean).join(" · ")}
                  </div>
                )}
                <div className="whitespace-pre-wrap">{c.id === p.id ? <Highlight text={c.text} quote={quote} /> : c.text}</div>
              </div>
            ))}
            {p.mentions.length > 0 && (
              <div className="pt-2 text-xs text-muted">
                Linked in the graph to:{" "}
                {p.mentions.map((m) => <span key={m} className="mr-1 rounded bg-bg px-1.5 py-0.5 font-mono">{m}</span>)}
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
