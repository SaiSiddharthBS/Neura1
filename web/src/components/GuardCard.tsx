"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { CalendarX, FileWarning, Quote, ShieldAlert, X } from "lucide-react";

export type Flag = {
  quote: string; severity: "error" | "warning" | "info"; title: string; message: string; record: string | null;
  evidence: { id: string; source: string; title: string; kind: string; author: string | null; ts: string | null; text: string }[];
};

const clip = (t: string, n = 190) => { const x = t.replace(/\s+/g, " ").trim(); return x.length > n ? `${x.slice(0, n - 1)}…` : x; };

/** "Neura1 remembers": shown while a message or draft is written, before anyone acts on it. */
export default function GuardCard({ flags, armed, nudge = 0, onDismiss }: {
  flags: Flag[]; armed?: boolean; nudge?: number; onDismiss?: () => void;
}) {
  const top = flags[0];
  const rest = flags.slice(1, 3);
  return (
    <AnimatePresence initial={false}>
      {top && (
        <motion.div key={top.title} role="alert"
                    initial={{ opacity: 0, y: 8, scale: 0.985 }} animate={{ opacity: 1, y: 0, scale: 1, x: nudge ? [0, -6, 6, -4, 4, 0] : 0 }}
                    exit={{ opacity: 0, y: 6, scale: 0.985 }} transition={{ type: "spring", stiffness: 420, damping: 32, x: { duration: 0.35 } }}
                    className={`mb-2 overflow-hidden rounded-2xl border ${top.severity === "error" ? "border-danger/35 bg-danger/[0.07]" : "border-warn/35 bg-warn/[0.07]"}`}>
          <div className="flex items-start gap-2.5 px-3.5 pt-3">
            <span className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full ${top.severity === "error" ? "bg-danger/15 text-danger" : "bg-warn/15 text-warn"}`}>
              {top.severity === "error" ? <ShieldAlert size={15} /> : top.title.includes("away") ? <CalendarX size={15} /> : <FileWarning size={15} />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Neura1 remembers</div>
              <div className="text-[13.5px] font-semibold text-ink">{top.title}</div>
              <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-soft">{top.message}</p>
            </div>
            {onDismiss && <button type="button" onClick={onDismiss} aria-label="Dismiss" className="rounded-md p-1 text-faint hover:bg-elev hover:text-ink"><X size={14} /></button>}
          </div>
          {top.evidence.length > 0 && (
            <div className="mt-2 space-y-1.5 px-3.5">
              {top.evidence.slice(0, 2).map((e) => (
                <div key={e.id} className="flex gap-2 rounded-xl bg-panel/70 px-2.5 py-1.5 text-[12px]">
                  <Quote size={12} className="mt-0.5 shrink-0 text-faint" />
                  <span className="min-w-0"><span className="text-ink-soft">“{clip(e.text)}”</span>
                    <span className="block text-[11px] text-muted">{e.title}{e.author ? ` · ${e.author}` : ""}{e.ts ? ` · ${e.ts.slice(0, 10)}` : ""}</span></span>
                </div>
              ))}
            </div>
          )}
          {rest.length > 0 && (
            <ul className="mt-2 space-y-0.5 px-3.5 text-[12px] text-muted">
              {rest.map((f) => <li key={f.title}>• <span className="text-ink-soft">{f.title}</span></li>)}
            </ul>
          )}
          <div className="mt-2.5 flex flex-wrap items-center gap-2 border-t border-line/70 px-3.5 py-2 text-[12px]">
            {top.record && <Link href={`/explore?id=${encodeURIComponent(top.record)}`} className="rounded-lg border border-line bg-panel px-2 py-0.5 hover:border-line2">Open {top.record} →</Link>}
            {top.severity === "error" && (
              <span className={`ml-auto ${armed ? "font-medium text-danger" : "text-muted"}`}>
                {armed ? "Press Enter again to send anyway" : "Edit the message, or send anyway with two presses of Enter"}
              </span>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
