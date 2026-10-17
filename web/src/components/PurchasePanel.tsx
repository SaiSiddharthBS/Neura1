"use client";

import { motion } from "motion/react";
import { AlertTriangle, Check, CheckCircle2, Copy, Loader2, Mail, Minus, PackagePlus, Plus, Sparkles, Truck, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, ApiError, inr } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";

type Draft = {
  status: "ok" | "needs_quote"; needed: boolean; item: { id: string; name: string };
  supplier: { id: string; name: string } | null; quote_id: string | null; unit_price: number | null; price_basis: string | null;
  qty: number; target: number; moq: number | null; total: number | null; saving_vs_notice: number | null;
  lead_weeks: number | null; lead_basis: string; expected_on: string | null; reaches: string[]; misses: string[];
  reasons: string[]; warnings: string[]; email: { to: string; subject: string; body: string } | null;
};
type Raised = { id: string; qty: number; total: number; expected_on: string | null; email: { subject: string; body: string } };

const fmt = (d: string | null) => (d ? new Date(d).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" }) : "—");
const errorText = (e: unknown) => (e instanceof ApiError && e.body && typeof e.body === "object" && "detail" in e.body
  ? String((e.body as { detail: unknown }).detail) : (e as Error).message);

/** Neura1 drafts the order from the records; a director or leader adjusts the quantity and approves it. */
export default function PurchasePanel({ item, onClose, onDone }: { item: string; onClose: () => void; onDone: () => void }) {
  const [d, setD] = useState<Draft | null>(null);
  const [qty, setQty] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [raised, setRaised] = useState<Raised | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api<Draft>(`/api/purchasing/draft?item=${encodeURIComponent(item)}`)
      .then((x) => { setD(x); setQty(x.qty); })
      .catch((e) => setError(errorText(e)));
  }, [item]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);

  const step = d?.moq && d.moq > 1 ? d.moq : 1;
  const total = d?.unit_price != null ? d.unit_price * qty : null;
  const email = raised?.email ?? (d?.email ? { ...d.email, body: d.email.body.replace(/Please supply [\d,]+ ×/, `Please supply ${qty.toLocaleString("en-IN")} ×`), subject: d.email.subject.replace(/[\d,]+ ×/, `${qty.toLocaleString("en-IN")} ×`) } : null);

  async function approve() {
    if (!d || !credentials()) return;
    setBusy(true); setError(null);
    try {
      const r = await api<Raised>("/api/purchasing/orders", { method: "POST", write: true, body: JSON.stringify({ item: d.item.id, qty }) });
      setRaised(r);
      toast.success(`${r.id} raised`, { description: `${r.qty.toLocaleString("en-IN")} × ${d.item.id}, expected ${fmt(r.expected_on)}` });
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.status === 403 && errorText(e).toLowerCase().includes("passcode")) forgetPasscode();
      setError(errorText(e));
    } finally { setBusy(false); }
  }

  async function copy() {
    if (!email) return;
    try { await navigator.clipboard.writeText(`Subject: ${email.subject}\n\n${email.body}`); setCopied(true); setTimeout(() => setCopied(false), 1600); } catch { /* the text is selectable */ }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/35 backdrop-blur-[2px]" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <motion.aside role="dialog" aria-label={`Purchase order for ${item}`} initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }}
                    transition={{ type: "spring", stiffness: 320, damping: 34 }}
                    className="surface-pop m-2 flex w-[min(520px,calc(100vw-1rem))] flex-col overflow-hidden rounded-[22px]">
        <header className="flex items-center gap-2 border-b border-line px-5 py-3.5">
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-gradient-to-br from-accent to-violet text-white"><PackagePlus size={16} /></span>
          <div className="min-w-0 flex-1">
            <div className="text-[14.5px] font-semibold">{raised ? `${raised.id} raised` : `Purchase order for ${item}`}</div>
            <div className="text-[12px] text-muted">{raised ? "On order now: stock, the promise check and the sandbox all count it" : "Drafted by Neura1 from the records. Nothing is ordered until you approve."}</div>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded-md p-1 text-faint hover:bg-elev hover:text-ink"><X size={16} /></button>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5" data-lenis-prevent>
          {!d && !error && <div className="grid h-40 place-items-center text-muted"><Loader2 className="animate-spin" size={18} /></div>}
          {error && <div className="rounded-xl border border-warn/30 bg-warn/[0.07] p-3 text-[13px] text-warn">{error}</div>}
          {d && raised && (
            <motion.div initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="rounded-2xl border border-success/30 bg-success/[0.08] p-5 text-center">
              <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 420, damping: 18, delay: 0.1 }}
                           className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-success text-white"><Check size={24} strokeWidth={3} /></motion.span>
              <div className="mt-3 text-[18px] font-semibold">{raised.id}</div>
              <div className="text-[13px] text-muted">{raised.qty.toLocaleString("en-IN")} × {d.item.id} from {d.supplier?.name} · {inr(raised.total)} · expected {fmt(raised.expected_on)}</div>
              <div className="mt-1 text-[12px] text-faint">Posted to #supply (without the price). Send the email below to the supplier.</div>
            </motion.div>
          )}
          {d && !raised && d.status === "needs_quote" && (
            <div className="rounded-2xl border border-warn/30 bg-warn/[0.07] p-4 text-[13px]">
              <div className="font-semibold text-warn">Request a quote first</div>
              <ul className="mt-1.5 space-y-1 text-ink-soft">{[...d.reasons, ...d.warnings].map((r) => <li key={r}>{r}</li>)}</ul>
            </div>
          )}
          {d && !raised && d.status === "ok" && !d.needed && (
            <div className="rounded-2xl border border-success/30 bg-success/[0.07] p-4 text-[13px]">
              <div className="flex items-center gap-2 font-semibold text-success"><CheckCircle2 size={15} /> Nothing to order</div>
              <ul className="mt-1.5 space-y-1 text-ink-soft">{d.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </div>
          )}
          {d && !raised && d.status === "ok" && d.needed && (
            <>
              <section className="rounded-2xl border border-line bg-elev/40 p-4">
                <div className="flex items-end gap-4">
                  <div>
                    <div className="text-[11.5px] text-muted">Quantity{d.moq && d.moq > 1 ? ` · multiples of ${d.moq}` : ""}</div>
                    <div className="mt-1 flex items-center gap-1.5">
                      <button onClick={() => setQty((q) => Math.max(step, q - step))} aria-label="Fewer" className="grid h-8 w-8 place-items-center rounded-lg border border-line hover:bg-elev"><Minus size={14} /></button>
                      <input value={qty} onChange={(e) => setQty(Math.max(0, Number(e.target.value.replace(/\D/g, "")) || 0))} aria-label="Quantity"
                             className="num w-24 rounded-lg border border-line px-2 py-1 text-center text-[20px] font-semibold" />
                      <button onClick={() => setQty((q) => q + step)} aria-label="More" className="grid h-8 w-8 place-items-center rounded-lg border border-line hover:bg-elev"><Plus size={14} /></button>
                    </div>
                    {qty !== d.qty && <button onClick={() => setQty(d.qty)} className="mt-1 text-[11.5px] text-accent hover:underline">Back to Neura1&apos;s {d.qty.toLocaleString("en-IN")}</button>}
                  </div>
                  <div className="ml-auto text-right">
                    <div className="text-[11.5px] text-muted">Total</div>
                    <motion.div key={total} initial={{ opacity: 0.4, y: -3 }} animate={{ opacity: 1, y: 0 }} className="num text-[24px] font-semibold tracking-tight">{total != null ? inr(total) : "—"}</motion.div>
                    <div className="text-[11.5px] text-muted">{d.unit_price != null ? `${inr(d.unit_price)} each` : ""}</div>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-[12.5px]">
                  <div className="rounded-xl bg-panel px-3 py-2"><div className="text-[11px] text-muted">Supplier</div><div className="font-medium">{d.supplier?.name}</div><div className="text-[11px] text-faint">{d.price_basis}</div></div>
                  <div className="rounded-xl bg-panel px-3 py-2"><div className="flex items-center gap-1 text-[11px] text-muted"><Truck size={11} /> Expected</div><div className="font-medium">{fmt(d.expected_on)}</div><div className="text-[11px] text-faint">{d.lead_weeks} weeks ({d.lead_basis === "notice" ? "supplier notice" : d.lead_basis === "history" ? "recent orders" : "quote"})</div></div>
                </div>
              </section>
              {d.saving_vs_notice ? (
                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex items-start gap-2.5 rounded-2xl border border-accent/30 bg-accent/[0.08] p-3.5 text-[13px]">
                  <Sparkles size={16} className="mt-0.5 shrink-0 text-accent" />
                  <span>Ordering now holds today&apos;s price: about <b>{inr((d.saving_vs_notice / d.qty) * qty)}</b> less than at the notified price.</span>
                </motion.div>
              ) : null}
              <section>
                <div className="mb-1.5 text-[11.5px] font-semibold uppercase tracking-[0.08em] text-faint">Why this order</div>
                <ul className="space-y-1.5 text-[13px]">{d.reasons.map((r) => <li key={r} className="flex gap-2"><CheckCircle2 size={14} className="mt-0.5 shrink-0 text-success" /><span>{r}</span></li>)}</ul>
              </section>
              {d.warnings.length > 0 && (
                <section className="space-y-1.5">
                  {d.warnings.map((w) => (
                    <div key={w} className={`flex gap-2 rounded-xl px-3 py-2 text-[12.5px] ${w.startsWith("Do not") ? "bg-danger/[0.08] text-ink" : "bg-warn/[0.08] text-ink"}`}>
                      <AlertTriangle size={14} className={`mt-0.5 shrink-0 ${w.startsWith("Do not") ? "text-danger" : "text-warn"}`} /><span>{w}</span>
                    </div>
                  ))}
                </section>
              )}
            </>
          )}
          {d && email && (d.needed || raised) && (
            <section>
              <div className="mb-1.5 flex items-center text-[11.5px] font-semibold uppercase tracking-[0.08em] text-faint"><Mail size={12} className="mr-1.5" /> Email to {d.supplier?.name}
                <button onClick={copy} className="ml-auto flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11.5px] normal-case tracking-normal text-muted hover:bg-elev hover:text-ink">
                  {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}</button></div>
              <div className="rounded-xl border border-line bg-panel p-3 text-[12.5px]">
                <div className="font-medium">{email.subject}</div>
                <pre className="mt-1.5 whitespace-pre-wrap font-sans text-ink-soft">{email.body}</pre>
              </div>
            </section>
          )}
        </div>

        {d && d.status === "ok" && d.needed && !raised && (
          <footer className="border-t border-line p-4">
            <button onClick={approve} disabled={busy || qty < 1}
                    className="press flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-[14px] font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-40">
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />} Approve and raise the order
            </button>
            <div className="mt-1.5 text-center text-[11px] text-faint">Price and supplier come from the records on the server, never from this form.</div>
          </footer>
        )}
      </motion.aside>
    </div>
  );
}
