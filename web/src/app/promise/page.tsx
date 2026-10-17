"use client";

import Link from "next/link";
import { motion } from "motion/react";
import {
  AlertTriangle, BadgeCheck, CalendarClock, CheckCircle2, CircleHelp, Cpu, Handshake, Loader2, Lock, ShieldCheck, Users, XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { PageTitle, Pill } from "@/components/ui";
import { api, ApiError, inr } from "@/lib/api";

type Constraint = {
  kind: "part" | "people" | "certification" | "revision"; subject: string; status: "ok" | "risk" | "blocker" | "unknown"; detail: string;
  need?: number; free?: number; short?: number; ready?: string; lead?: { weeks: number | null; basis: string; source: string | null; quote_weeks: number | null };
};
type Result = {
  status: string; verdict: "yes" | "at_risk" | "unconfirmed" | "no"; headline: string; product: string; revision: string; qty: number;
  due: string; today: string; earliest: string | null; limiting: string | null; constraints: Constraint[]; fixes: string[];
  stock_and_quote_says: { verdict: "yes" | "no"; ready: string | null; note: string }; purchase_value: number | null;
  leave_included: boolean; assumptions: string[]; message?: string;
};
type Product = { product: string; name: string; revision: string; status: string };

const EXAMPLES = [
  { product: "PDU-28", qty: 50, due: "2026-12-31", label: "50 × PDU-28 by 31 Dec" },
  { product: "BCU-24", qty: 20, due: "2026-12-20", label: "20 × BCU-24 by 20 Dec" },
  { product: "PDU-28", qty: 15, due: "2027-05-15", label: "15 × PDU-28 by 15 May" },
];

const VERDICT = {
  yes: { word: "Yes", tone: "text-success", ring: "border-success/35 from-success/[0.12]", icon: CheckCircle2 },
  at_risk: { word: "Yes, with risks", tone: "text-warn", ring: "border-warn/35 from-warn/[0.12]", icon: AlertTriangle },
  unconfirmed: { word: "Not confirmed", tone: "text-warn", ring: "border-warn/35 from-warn/[0.10]", icon: CircleHelp },
  no: { word: "No", tone: "text-danger", ring: "border-danger/35 from-danger/[0.12]", icon: XCircle },
} as const;

const STATUS = {
  ok: { icon: CheckCircle2, cls: "text-success" }, risk: { icon: AlertTriangle, cls: "text-warn" },
  blocker: { icon: XCircle, cls: "text-danger" }, unknown: { icon: CircleHelp, cls: "text-warn" },
} as const;

const GROUPS: { kind: Constraint["kind"]; title: string; icon: typeof Cpu }[] = [
  { kind: "revision", title: "Revision", icon: BadgeCheck },
  { kind: "part", title: "Parts and supply", icon: Cpu },
  { kind: "people", title: "People and knowledge", icon: Users },
  { kind: "certification", title: "Certifications", icon: ShieldCheck },
];

const fmt = (d: string | null) => (d ? new Date(d).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" }) : "—");

export default function PromisePage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [product, setProduct] = useState("PDU-28");
  const [qty, setQty] = useState(50);
  const [due, setDue] = useState("2026-12-31");
  const [r, setR] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api<Product[]>("/api/promise/products").then(setProducts).catch(() => {}); }, []);

  async function check(p = product, q = qty, d = due) {
    setBusy(true); setError(null);
    try {
      const res = await api<Result>("/api/promise", { method: "POST", body: JSON.stringify({ product: p, qty: q, due: d }) });
      if (res.status !== "ok") setError(res.message ?? "Could not check that"); else setR(res);
    } catch (e) {
      setError(e instanceof ApiError ? String((e.body as { detail?: unknown })?.detail ?? e.message) : (e as Error).message);
    } finally { setBusy(false); }
  }

  const v = r ? VERDICT[r.verdict] : null;
  const field = "rounded-xl border border-line bg-panel px-3 py-2 text-[14px]";

  return (
    <div className="space-y-5">
      <div>
        <PageTitle>Can we <em>promise</em> this?</PageTitle>
        <p className="mt-1 max-w-3xl text-sm text-muted">Ask before you commit to a customer. Neura1 checks the parts, the newest supplier notices, the people and knowledge the product depends on, and its certifications. The checks are done by code, and every step is shown.</p>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); check(); }} className="card flex flex-wrap items-end gap-3 p-4">
        <label className="text-[12px] text-muted">Product or revision
          <select value={product} onChange={(e) => setProduct(e.target.value)} className={`mt-1 block w-56 ${field}`}>
            {[...new Map(products.map((p) => [p.product, p])).values()].map((p) => <option key={p.product} value={p.product}>{p.product} · released revision</option>)}
            {products.map((p) => <option key={p.revision} value={p.revision}>{p.revision} · {p.status}</option>)}
          </select>
        </label>
        <label className="text-[12px] text-muted">Quantity
          <input type="number" min={1} max={100000} value={qty} onChange={(e) => setQty(Number(e.target.value))} className={`mt-1 block w-28 ${field}`} />
        </label>
        <label className="text-[12px] text-muted">Delivery date
          <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className={`mt-1 block w-44 ${field}`} />
        </label>
        <button disabled={busy || qty < 1} className="press flex items-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-[14px] font-medium text-accent-ink transition hover:bg-accent-hover disabled:opacity-40">
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Handshake size={15} />} Check
        </button>
        <div className="flex w-full flex-wrap gap-1.5 pt-1">
          {EXAMPLES.map((x) => (
            <button type="button" key={x.label} onClick={() => { setProduct(x.product); setQty(x.qty); setDue(x.due); check(x.product, x.qty, x.due); }}
                    className="rounded-full border border-line px-3 py-1 text-[12px] text-muted transition hover:border-accent/40 hover:text-ink">{x.label}</button>
          ))}
        </div>
        {error && <div className="w-full text-[12.5px] text-warn">{error}</div>}
      </form>

      {r && v && (
        <motion.div key={`${r.revision}-${r.qty}-${r.due}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                    className={`space-y-4 ${busy ? "opacity-60" : ""}`}>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <section className={`relative overflow-hidden rounded-[22px] border bg-gradient-to-br to-transparent p-6 ${v.ring}`}>
              <div className="flex items-center gap-2 text-[12px] font-medium text-muted"><CalendarClock size={14} /> {r.qty} × {r.revision} by {fmt(r.due)}</div>
              <div className={`mt-2 flex items-center gap-3 text-[40px] font-semibold leading-none tracking-tight ${v.tone}`}>
                <v.icon size={34} strokeWidth={2.2} /> {v.word}
              </div>
              <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-ink">{r.headline.replace(/^(No|Yes)\.\s*/, "")}</p>
              <Timeline r={r} />
            </section>
            <section className="card flex flex-col p-5">
              <div className="text-[12px] font-semibold uppercase tracking-[0.08em] text-faint">Two answers to the same question</div>
              <div className="mt-3 grid flex-1 grid-cols-2 gap-3">
                <div className="rounded-2xl border border-line bg-elev/50 p-3.5">
                  <div className="text-[11.5px] text-muted">Stock and quotes alone</div>
                  <div className={`mt-1 text-[22px] font-semibold ${r.stock_and_quote_says.verdict === "yes" ? "text-success" : "text-danger"}`}>{r.stock_and_quote_says.verdict === "yes" ? "Yes" : "No"}</div>
                  <div className="mt-0.5 text-[12px] text-muted">{r.stock_and_quote_says.ready ? `ready ${fmt(r.stock_and_quote_says.ready)}` : "from free stock"}</div>
                </div>
                <div className="rounded-2xl border border-accent/30 bg-accent/[0.07] p-3.5">
                  <div className="text-[11.5px] text-muted">Neura1, from the whole graph</div>
                  <div className={`mt-1 text-[22px] font-semibold ${v.tone}`}>{v.word}</div>
                  <div className="mt-0.5 text-[12px] text-muted">{r.earliest ? `earliest ${fmt(r.earliest)}` : r.verdict === "unconfirmed" ? "lead time missing" : "on the date"}</div>
                </div>
              </div>
              <p className="mt-3 text-[12px] leading-relaxed text-muted">
                {r.stock_and_quote_says.verdict !== (r.verdict === "no" ? "no" : "yes")
                  ? "They disagree. A stock-and-quote check misses the newest supplier notices, the people and knowledge the product depends on, and its certifications."
                  : "They agree here; Neura1 also checked supplier notices, people and certifications."}
              </p>
              {r.purchase_value !== null && <div className="mt-2 text-[12px] text-muted">Purchase needed at today&apos;s terms: <b className="text-ink">{inr(r.purchase_value)}</b></div>}
            </section>
          </div>

          {r.fixes.length > 0 && (
            <section className="card p-5">
              <div className="text-[12px] font-semibold uppercase tracking-[0.08em] text-faint">What would change the answer</div>
              <ol className="mt-2 space-y-1.5">
                {r.fixes.map((f, i) => (
                  <motion.li key={f} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}
                             className="flex gap-3 text-[13.5px]"><span className="num mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-elev-strong text-[11px] text-muted">{i + 1}</span>
                    <span>{f.includes("Knowledge rescue") ? <>{f.replace(" (Knowledge rescue).", ".")} <Link href="/rescue" className="text-accent hover:underline">Open Knowledge rescue →</Link></> : f}</span></motion.li>
                ))}
              </ol>
            </section>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            {GROUPS.map((g) => {
              const items = r.constraints.filter((c) => c.kind === g.kind);
              if (!items.length && g.kind !== "people") return null;
              return (
                <section key={g.kind} className="card p-5">
                  <h2 className="flex items-center gap-2 text-[14px] font-semibold"><g.icon size={15} className="text-muted" /> {g.title}</h2>
                  <ul className="mt-2 space-y-2">
                    {items.map((c) => {
                      const S = STATUS[c.status];
                      return (
                        <li key={c.subject} className="flex gap-2.5 text-[13px]">
                          <S.icon size={16} className={`mt-0.5 shrink-0 ${S.cls}`} />
                          <span className="min-w-0"><Link href={c.kind === "people" ? "/people" : `/explore?id=${encodeURIComponent(c.subject)}`} className="font-medium hover:underline">{c.subject}</Link>
                            <span className="text-muted"> · {c.detail}</span>
                            {c.lead?.basis === "notice" && <span className="ml-1"><Pill tone="violet">supplier notice</Pill></span>}</span>
                        </li>
                      );
                    })}
                    {g.kind === "people" && !items.length && (
                      <li className="flex gap-2.5 text-[13px] text-muted">
                        {r.leave_included ? <><CheckCircle2 size={16} className="text-success" /> Nobody it depends on is away before the date.</>
                          : <><Lock size={15} /> Leave plans are weighed for the directors and leadership team.</>}
                      </li>
                    )}
                  </ul>
                </section>
              );
            })}
          </div>
          <ul className="space-y-0.5 px-1 text-[11.5px] text-faint">{r.assumptions.map((a) => <li key={a}>· {a}</li>)}</ul>
        </motion.div>
      )}
    </div>
  );
}

/** Today, the promised date and the earliest realistic date, to scale. */
function Timeline({ r }: { r: Result }) {
  const t0 = new Date(r.today).getTime();
  // The promised date is labelled above the track, the others below, so close dates never collide.
  const points = [{ at: r.due, label: "Promised", cls: "bg-ink", above: true }];
  if (r.earliest) points.push({ at: r.earliest, label: "Earliest", cls: r.verdict === "no" ? "bg-danger" : "bg-success", above: false });
  if (r.stock_and_quote_says.ready) points.push({ at: r.stock_and_quote_says.ready, label: "Quotes say", cls: "bg-muted", above: false });
  const end = Math.max(...points.map((p) => new Date(p.at).getTime())) + 7 * 864e5;
  const x = (d: string) => `${Math.min(100, Math.max(0, ((new Date(d).getTime() - t0) / (end - t0)) * 100))}%`;
  return (
    <div className="relative mt-10 h-16">
      <div className="absolute left-0 right-0 top-3 h-1 rounded-full bg-elev-strong" />
      {r.earliest && (
        <motion.div className={`absolute top-3 h-1 rounded-full ${r.verdict === "no" ? "bg-danger/60" : "bg-success/60"}`}
                    initial={{ width: 0 }} animate={{ width: x(r.earliest) }} transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }} />
      )}
      <span className="absolute left-0 top-6 text-[10.5px] text-muted">Today</span>
      {points.map((p) => (
        <motion.div key={p.label} className="absolute top-1.5 -translate-x-1/2" style={{ left: x(p.at) }} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
          {p.above && <div className="absolute bottom-full mb-1.5 left-1/2 -translate-x-1/2 whitespace-nowrap text-center text-[10.5px] leading-tight text-muted">{p.label}<br /><span className="text-ink-soft">{fmt(p.at)}</span></div>}
          <div className={`mx-auto h-4 w-4 rounded-full border-2 border-[var(--bg)] ${p.cls}`} />
          {!p.above && <div className="mt-1 whitespace-nowrap text-center text-[10.5px] leading-tight text-muted">{p.label}<br /><span className="text-ink-soft">{fmt(p.at)}</span></div>}
        </motion.div>
      ))}
    </div>
  );
}
