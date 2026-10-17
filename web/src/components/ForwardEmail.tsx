"use client";

import { Inbox, Loader2, MailPlus } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { viewerId } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";

type Done = { file: string; kind?: string; source_id?: string; error?: string; model_error?: string | null };
const KIND = { notice: "supplier notice", escalation: "customer escalation", leave: "leave notice" } as Record<string, string>;

/** Forward an email (or drop a notice) and Neura1 classifies it, reads it and opens the right analysis. */
export default function ForwardEmail({ onAdded }: { onAdded?: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [done, setDone] = useState<Done[]>([]);

  async function send(f: File) {
    const c = credentials();
    if (!c) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", f);
      const res = await fetch("/api/inbox", { method: "POST", body: form,
        headers: { "x-neura1-as": viewerId(), "x-demo-passcode": c.pass } });
      const body = await res.json().catch(() => ({}));
      if (res.status === 403) forgetPasscode();
      if (!res.ok) throw new Error(body.detail ?? "Could not read the file");
      const items: Done[] = body.processed ?? [];
      setDone(items);
      const first = items.find((x) => !x.error);
      if (first) toast.success(`Read as a ${KIND[first.kind ?? ""] ?? "signal"}`, { description: "It is now in the graph and in the right chat channel." });
      onAdded?.();
    } catch (e) {
      toast.error("Could not take the file", { description: (e as Error).message });
    } finally { setBusy(false); }
  }

  return (
    <div className="card mt-5 p-4">
      <div className="flex items-center gap-2 text-[14px] font-semibold tracking-tight"><MailPlus size={15} className="text-accent" /> Forward an email</div>
      <p className="mt-1 text-[13px] text-muted">
        Drop a forwarded email (.eml) or a notice (.pdf, .md, .txt). Neura1 decides whether it is a supplier change, a customer
        escalation or a leave notice, reads it, links it to what it names and tells the right channel. Files saved into the
        server&apos;s <span className="font-mono text-[12px]">data/mail-drop</span> folder are picked up the same way, every few seconds.
      </p>
      <button onClick={() => input.current?.click()} disabled={busy}
              onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
              onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) send(f); }}
              className={`mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-5 text-[13px] transition ${over ? "border-accent bg-accent/[0.07] text-ink" : "border-line2 text-muted hover:border-accent/60 hover:text-ink"}`}>
        {busy ? <Loader2 size={15} className="animate-spin" /> : <Inbox size={15} />} {busy ? "Reading…" : "Drop an email here, or choose a file"}
      </button>
      <input ref={input} type="file" hidden accept=".eml,.pdf,.md,.txt" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) send(f); }} />
      {done.length > 0 && (
        <ul className="mt-3 space-y-1 text-[12.5px]">
          {done.map((d, i) => (
            <li key={i} className={d.error ? "text-danger" : "text-ink-soft"}>
              {d.file}: {d.error ? d.error : `${KIND[d.kind ?? ""] ?? d.kind}${d.model_error ? ` (facts still need entering: ${d.model_error})` : ""}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
