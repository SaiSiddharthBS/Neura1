"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import {
  ArrowDownLeft, ArrowUpRight, Boxes, Brain, CalendarClock, CheckCircle2, Clock3, Handshake, Lock, MapPin, PackageCheck,
  Search, ShieldAlert, Sparkles, Truck, Waypoints,
} from "lucide-react";
import { Suspense, useEffect, useMemo, useState } from "react";
import { PageTitle, Pill, Ticker } from "@/components/ui";
import { api, inr } from "@/lib/api";

type Row = {
  id: string; name: string; mpn: string | null; manufacturer: string | null; category: string | null; location: string | null;
  reorder_level: number | null; on_hand: number | null; allocated: number | null; free: number | null;
  status: "ok" | "below_reorder" | "short" | "no_record"; available: number | null; planned_need: number; on_order: number; next_delivery: string | null;
  last_price: number | null; stock_value: number | null; orders: number;
  last_order: { id: string; ordered_on: string; supplier: string; qty: number; unit_price: string | null } | null;
};
type Order = {
  id: string; qty: number; unit_price: string | null; ordered_on: string; expected_on: string | null; status: string;
  supplier: string; quote: string | null; received_on: string | null; received_qty: number; rejected_qty: number;
  lead_days: number | null; on_time: boolean | null; receipts: { id: string; qty: number; received_on: string; lot: string; rejected: number; note: string | null }[];
};
type Price = { date: string; until?: string; price: number | null; kind: "paid" | "quoted" | "notice"; ref: string; supplier: string | null; qty?: number };
type Move = { id: string; date: string; qty: number; kind: string; ref: string | null; note: string | null; balance: number };
type Detail = {
  item: { id: string; name: string; mpn: string | null; manufacturer: string | null; category: string | null; uom: string | null; hsn: string | null; location: string | null; reorder_level: number | null };
  stock: { on_hand: number | null; allocated: number | null; free: number | null; available: number | null; status: Row["status"]; on_order: number; next_delivery: string | null; stock_value: number | null; last_price: number | null };
  last_order: Order | null; last_received: Order | null; orders: Order[]; price_history: Price[]; ledger: Move[];
  suppliers: { name: string; orders: number; qty: number; on_time: number; delivered: number; rejected: number; last_price: string | null; last_ordered: string; avg_lead_days: number | null }[];
  demand: { build: string; revision: string; planned_date: string; units: number; need: number }[]; planned_need: number;
  where_used: { revision: string; product: string; status: string; per_unit: number }[];
  owner: { id: string; name: string } | null; decisions: { id: string; outcome: string; summary: string }[];
  alternates: { id: string; status: string; note: string }[]; insights: string[]; money_visible: boolean; today: string;
};

const STATUS: Record<Row["status"], { label: string; tone: "danger" | "warn" | "success" | "neutral" }> = {
  short: { label: "Short for builds", tone: "danger" }, below_reorder: { label: "Time to order", tone: "warn" },
  ok: { label: "Covered", tone: "success" }, no_record: { label: "Not stocked", tone: "neutral" },
};
const fmt = (d: string | null | undefined) => (d ? new Date(d).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" }) : "—");
const num = (n: number | null | undefined) => (n === null || n === undefined ? "—" : n.toLocaleString("en-IN"));

export default function InventoryPage() {
  return <Suspense fallback={null}><Inventory /></Suspense>;
}

function Inventory() {
  const params = useSearchParams();
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [q, setQ] = useState("");
  const [d, setD] = useState<Detail | null>(null);
  const selected = params.get("item") ?? rows.find((r) => r.status === "below_reorder")?.id ?? rows[0]?.id ?? null;

  useEffect(() => { api<Row[]>("/api/inventory").then(setRows).catch(() => {}); }, []);
  useEffect(() => {
    if (!selected) return;
    let live = true;
    api<Detail>(`/api/inventory/${encodeURIComponent(selected)}`).then((x) => live && setD(x)).catch(() => {});
    return () => { live = false; };
  }, [selected]);

  const shown = useMemo(() => rows.filter((r) => !q || `${r.id} ${r.name} ${r.category} ${r.mpn}`.toLowerCase().includes(q.toLowerCase())), [rows, q]);
  const below = rows.filter((r) => r.status === "below_reorder" || r.status === "short").length;
  const onOrder = rows.filter((r) => r.on_order > 0).length;
  const value = rows.reduce((s, r) => s + (r.stock_value ?? 0), 0);
  const moneyVisible = rows.some((r) => r.last_price !== null);

  return (
    <div className="space-y-5">
      <div>
        <PageTitle>What Flyvi <em>holds</em></PageTitle>
        <p className="mt-1 max-w-3xl text-sm text-muted">Stock, purchase orders, deliveries and prices, sitting next to the products, builds, suppliers and decisions they belong to. Every movement is one row in a stock ledger, so the numbers always add up. Ask Neura1 anything about a part.</p>
      </div>

      <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
        <Tile label="Parts tracked" value={rows.length} />
        <Tile label="Need ordering" value={below} tone={below ? "text-danger" : ""} />
        <Tile label="Parts on order" value={onOrder} />
        <Tile label="Stock value at last price" money={moneyVisible ? value : null} />
      </div>

      <div className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="card h-fit overflow-hidden">
          <div className="p-3">
            <label className="flex items-center gap-2 rounded-xl border border-line bg-elev px-3 py-1.5 text-[13px] focus-within:border-accent/50">
              <Search size={14} className="text-faint" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search parts" className="min-w-0 flex-1 bg-transparent outline-none" style={{ background: "transparent" }} />
            </label>
          </div>
          <ul className="max-h-[70vh] space-y-0.5 overflow-y-auto px-2 pb-2" data-lenis-prevent>
            {shown.map((r) => {
              const on = r.id === selected;
              // After the planned builds, plus what is on order, against twice the reorder level (the tick is the level).
              const left = (r.available ?? 0) + r.on_order;
              const pct = r.reorder_level ? Math.min(100, (left / (r.reorder_level * 2)) * 100) : left ? 100 : 0;
              return (
                <li key={r.id}>
                  <button onClick={() => router.replace(`/inventory?item=${encodeURIComponent(r.id)}`, { scroll: false })} aria-current={on}
                          className={`w-full rounded-xl px-3 py-2.5 text-left transition ${on ? "bg-accent/12 ring-1 ring-accent/25" : "hover:bg-elev"}`}>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[13px] font-semibold">{r.id}</span>
                      <span className="ml-auto"><Pill tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Pill></span>
                    </div>
                    <div className="mt-0.5 truncate text-[12px] text-muted">{r.name}</div>
                    {r.on_hand !== null && (
                      <div className="mt-2 flex items-center gap-2">
                        <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-elev-strong">
                          <motion.div className={`absolute inset-y-0 left-0 rounded-full ${r.status === "ok" ? "bg-success" : r.status === "below_reorder" ? "bg-warn" : "bg-danger"}`}
                                      initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }} />
                          {r.reorder_level ? <span className="absolute inset-y-0 left-1/2 w-px bg-ink/50" title="Reorder level" /> : null}
                        </div>
                        <span className="num w-28 text-right text-[11px] text-muted">{num(r.available)} after builds</span>
                      </div>
                    )}
                    {r.on_order > 0 && <div className="mt-1 flex items-center gap-1 text-[11px] text-accent"><Truck size={11} /> {num(r.on_order)} on order · {fmt(r.next_delivery)}</div>}
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        <AnimatePresence mode="wait">
          {d && (
            <motion.div key={d.item.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                        className="min-w-0 space-y-4">
              <section className="card p-5">
                <div className="flex flex-wrap items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="font-mono text-[26px] font-semibold tracking-tight">{d.item.id}</h2>
                      <Pill tone={STATUS[d.stock.status].tone} dot>{STATUS[d.stock.status].label}</Pill>
                    </div>
                    <div className="text-[14px] text-ink-soft">{d.item.name}</div>
                    <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted">
                      {d.item.manufacturer && <span>{d.item.manufacturer} · {d.item.mpn}</span>}
                      {d.item.category && <span>{d.item.category}</span>}
                      {d.item.hsn && <span>HSN {d.item.hsn}</span>}
                      {d.item.location && <span className="flex items-center gap-1"><MapPin size={11} /> {d.item.location}</span>}
                      {d.owner && <Link href={`/people?id=${d.owner.id}`} className="hover:text-ink">Owner: {d.owner.name}</Link>}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link href={`/brain?ask=${encodeURIComponent(`Tell me everything about ${d.item.id}: stock, orders, prices and what depends on it`)}`}
                          className="press flex items-center gap-1.5 rounded-xl bg-accent px-3 py-1.5 text-[12.5px] font-medium text-accent-ink hover:bg-accent-hover"><Brain size={13} /> Ask about it</Link>
                    <Link href={`/explore?id=${encodeURIComponent(d.item.id)}`} className="flex items-center gap-1.5 rounded-xl border border-line px-3 py-1.5 text-[12.5px] text-muted hover:border-line2 hover:text-ink"><Waypoints size={13} /> In the graph</Link>
                    {d.where_used.some((w) => w.status === "released") && <Link href="/promise" className="flex items-center gap-1.5 rounded-xl border border-line px-3 py-1.5 text-[12.5px] text-muted hover:border-line2 hover:text-ink"><Handshake size={13} /> Can we promise?</Link>}
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2.5 md:grid-cols-4 xl:grid-cols-7">
                  <Mini label="On hand" value={d.stock.on_hand} />
                  <Mini label="Allocated" value={d.stock.allocated} />
                  <Mini label="Free" value={d.stock.free} />
                  <Mini label="Planned builds need" value={d.planned_need} />
                  <Mini label="Left after builds" value={d.stock.available} sub={d.item.reorder_level ? `reorder at ${num(d.item.reorder_level)}` : undefined} tone={d.stock.status === "ok" ? "" : "text-danger"} />
                  <Mini label="On order" value={d.stock.on_order} sub={d.stock.next_delivery ? `due ${fmt(d.stock.next_delivery)}` : undefined} />
                  <Mini label="Last price paid" text={d.money_visible ? (d.stock.last_price !== null ? inr(d.stock.last_price) : "—") : "hidden"} />
                </div>
              </section>

              {d.insights.length > 0 && (
                <section className="rounded-[22px] border border-accent/25 bg-gradient-to-br from-accent/[0.08] via-violet/[0.04] to-transparent p-5">
                  <div className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-accent"><Sparkles size={13} /> What Neura1 sees</div>
                  <ul className="mt-2 space-y-1.5">
                    {d.insights.map((s, i) => (
                      <motion.li key={s} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }} className="flex gap-2 text-[13.5px]">
                        {s.startsWith("Do not") ? <ShieldAlert size={15} className="mt-0.5 shrink-0 text-danger" /> : <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-faint" />}<span>{s}</span>
                      </motion.li>
                    ))}
                  </ul>
                </section>
              )}

              <div className="grid gap-4 xl:grid-cols-2">
                <section className="card p-5">
                  <h3 className="text-[14px] font-semibold">Price history</h3>
                  {d.money_visible ? <PriceChart points={d.price_history} today={d.today} />
                    : <div className="mt-3 flex items-center gap-2 text-[13px] text-muted"><Lock size={14} /> Prices are visible to the directors and leadership team.</div>}
                </section>
                <section className="card p-5">
                  <h3 className="text-[14px] font-semibold">Stock over time</h3>
                  <BalanceChart moves={d.ledger} reorder={d.item.reorder_level} today={d.today} />
                </section>
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <section className="card p-5">
                  <h3 className="flex items-center gap-2 text-[14px] font-semibold"><Clock3 size={15} className="text-muted" /> Last ordered</h3>
                  {d.last_order ? (
                    <div className="mt-2 space-y-1 text-[13.5px]">
                      <div><span className="font-mono font-semibold">{d.last_order.id}</span> · {num(d.last_order.qty)} from <b>{d.last_order.supplier}</b>{d.money_visible && d.last_order.unit_price ? <> at <b>{inr(Number(d.last_order.unit_price))}</b></> : null}</div>
                      <div className="text-muted">Ordered {fmt(d.last_order.ordered_on)} · expected {fmt(d.last_order.expected_on)}{d.last_order.received_on ? ` · received ${fmt(d.last_order.received_on)}` : ""}</div>
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        <Pill tone={d.last_order.status === "open" ? "accent" : "neutral"}>{d.last_order.status}</Pill>
                        {d.last_order.on_time !== null && <Pill tone={d.last_order.on_time ? "success" : "warn"}>{d.last_order.on_time ? "on time" : "late"}</Pill>}
                        {d.last_order.lead_days !== null && <Pill>{d.last_order.lead_days} days</Pill>}
                        {d.last_order.quote && <Pill tone="violet">{d.last_order.quote}</Pill>}
                        {d.last_order.receipts[0] && <Pill>lot {d.last_order.receipts[0].lot}</Pill>}
                      </div>
                    </div>
                  ) : <p className="mt-2 text-[13px] text-muted">No purchase is on record.</p>}
                </section>
                <section className="card p-5">
                  <h3 className="flex items-center gap-2 text-[14px] font-semibold"><Truck size={15} className="text-muted" /> Suppliers</h3>
                  {d.suppliers.length ? (
                    <div className="mt-2 overflow-x-auto"><table className="w-full text-[13px]">
                      <thead><tr className="text-left text-[11.5px] text-muted"><th className="py-1 font-medium">Supplier</th><th className="font-medium">Orders</th><th className="font-medium">On time</th><th className="font-medium">Avg days</th><th className="font-medium">Rejected</th></tr></thead>
                      <tbody>{d.suppliers.map((s) => (
                        <tr key={s.name} className="border-t border-line"><td className="py-1.5 pr-2">{s.name}</td><td className="num">{s.orders}</td><td className="num">{s.on_time}/{s.delivered}</td><td className="num">{s.avg_lead_days ?? "—"}</td><td className="num">{s.rejected}</td></tr>
                      ))}</tbody>
                    </table></div>
                  ) : <p className="mt-2 text-[13px] text-muted">No supplier on record.</p>}
                </section>
              </div>

              <section className="card p-5">
                <h3 className="flex items-center gap-2 text-[14px] font-semibold"><PackageCheck size={15} className="text-muted" /> Purchase orders and deliveries</h3>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full min-w-[640px] text-[13px]">
                    <thead><tr className="text-left text-[11.5px] text-muted"><th className="py-1 font-medium">Order</th><th className="font-medium">Supplier</th><th className="font-medium">Qty</th>{d.money_visible && <th className="font-medium">Price</th>}<th className="font-medium">Ordered</th><th className="font-medium">Received</th><th className="font-medium">Days</th><th className="font-medium">Status</th></tr></thead>
                    <tbody>{d.orders.map((o) => (
                      <tr key={o.id} className="border-t border-line">
                        <td className="py-1.5 pr-2 font-mono">{o.id}</td><td className="pr-2">{o.supplier}</td><td className="num">{num(o.qty)}{o.rejected_qty ? <span className="text-warn"> (−{o.rejected_qty})</span> : null}</td>
                        {d.money_visible && <td className="num">{o.unit_price ? inr(Number(o.unit_price)) : "—"}</td>}
                        <td>{fmt(o.ordered_on)}</td><td>{o.received_on ? fmt(o.received_on) : <span className="text-accent">due {fmt(o.expected_on)}</span>}</td>
                        <td className="num">{o.lead_days ?? "—"}</td>
                        <td>{o.status === "open" ? <Pill tone="accent">open</Pill> : o.on_time === false ? <Pill tone="warn">late</Pill> : <Pill tone="success">received</Pill>}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                  {!d.orders.length && <p className="text-[13px] text-muted">No purchase orders on record.</p>}
                </div>
              </section>

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
                <section className="card p-5">
                  <h3 className="flex items-center gap-2 text-[14px] font-semibold"><Boxes size={15} className="text-muted" /> Stock ledger</h3>
                  <div className="mt-2 max-h-80 overflow-y-auto" data-lenis-prevent>
                    <table className="w-full text-[13px]">
                      <thead className="sticky top-0" style={{ background: "var(--panel)" }}><tr className="text-left text-[11.5px] text-muted"><th className="py-1 font-medium">Date</th><th className="font-medium">Movement</th><th className="text-right font-medium">Qty</th><th className="text-right font-medium">Balance</th></tr></thead>
                      <tbody>{[...d.ledger].reverse().map((m) => (
                        <tr key={m.id} className="border-t border-line">
                          <td className="py-1.5 pr-2 whitespace-nowrap text-muted">{fmt(m.date)}</td>
                          <td className="pr-2"><span className="flex items-center gap-1.5">{m.qty > 0 ? <ArrowDownLeft size={13} className="text-success" /> : <ArrowUpRight size={13} className="text-danger" />}<span className="truncate">{m.note}</span></span></td>
                          <td className={`num text-right ${m.qty > 0 ? "text-success" : "text-danger"}`}>{m.qty > 0 ? "+" : ""}{num(m.qty)}</td>
                          <td className="num text-right font-medium">{num(m.balance)}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                    {!d.ledger.length && <p className="text-[13px] text-muted">No movements on record.</p>}
                  </div>
                </section>
                <div className="space-y-4">
                  <section className="card p-5">
                    <h3 className="flex items-center gap-2 text-[14px] font-semibold"><CalendarClock size={15} className="text-muted" /> What the planned builds need</h3>
                    <ul className="mt-2 space-y-1 text-[13px]">
                      {d.demand.map((x) => <li key={x.build} className="flex gap-2"><span className="font-mono">{x.build}</span><span className="text-muted">{x.units} × {x.revision} on {fmt(x.planned_date)}</span><span className="num ml-auto font-medium">{num(x.need)}</span></li>)}
                      {!d.demand.length && <li className="text-muted">No planned build uses it.</li>}
                    </ul>
                  </section>
                  <section className="card p-5">
                    <h3 className="text-[14px] font-semibold">Where it is used, and what was decided</h3>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {d.where_used.map((w) => <Link key={w.revision} href={`/explore?id=${w.revision}`}><Pill tone={w.status === "released" ? "accent" : "neutral"}>{w.revision} · {w.per_unit}/unit · {w.status}</Pill></Link>)}
                    </div>
                    <ul className="mt-3 space-y-1 text-[12.5px]">
                      {d.decisions.slice(0, 4).map((x) => <li key={x.id}><Link href={`/explore?id=${x.id}`} className="font-mono hover:underline">{x.id}</Link> <span className="text-muted">({x.outcome}) {x.summary}</span></li>)}
                      {d.alternates.map((a) => <li key={a.id}>Alternate <span className="font-mono">{a.id}</span>: <span className={a.status === "rejected" ? "text-danger" : "text-muted"}>{a.status}</span></li>)}
                    </ul>
                  </section>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function Tile({ label, value, money, tone = "" }: { label: string; value?: number; money?: number | null; tone?: string }) {
  return (
    <div className="card p-3.5">
      <div className="text-[11.5px] text-muted">{label}</div>
      <div className={`mt-1 text-[22px] font-semibold tracking-tight ${tone}`}>
        {money !== undefined ? (money === null ? <span className="flex items-center gap-1.5 text-[14px] font-normal text-muted"><Lock size={13} /> hidden</span> : <Ticker value={money} format={(n) => inr(Math.round(n))} />) : <Ticker value={value ?? 0} />}
      </div>
    </div>
  );
}

function Mini({ label, value, text, sub, tone = "" }: { label: string; value?: number | null; text?: string; sub?: string; tone?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-elev/40 p-3">
      <div className="text-[11px] text-muted">{label}</div>
      <div className={`num mt-0.5 text-[18px] font-semibold ${tone}`}>{text ?? num(value)}</div>
      {sub && <div className="text-[11px] text-faint">{sub}</div>}
    </div>
  );
}

const CW = 520, CH = 200, PAD = { l: 44, r: 14, t: 14, b: 26 };

/** Prices paid (line and dots), quotes (bars across their validity) and the supplier notice (a diamond), to scale. */
function PriceChart({ points, today }: { points: Price[]; today: string }) {
  const valid = points.filter((p) => p.price !== null && p.date);
  if (!valid.length) return <p className="mt-2 text-[13px] text-muted">No price on record.</p>;
  const dates = valid.flatMap((p) => [p.date, p.until ?? p.date]).concat(today).map((d) => new Date(d).getTime());
  const t0 = Math.min(...dates), t1 = Math.max(...dates) || t0 + 1;
  const prices = valid.map((p) => p.price as number);
  const lo = Math.min(...prices) * 0.9, hi = Math.max(...prices) * 1.06;
  const x = (d: string) => PAD.l + ((new Date(d).getTime() - t0) / (t1 - t0 || 1)) * (CW - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo || 1)) * (CH - PAD.t - PAD.b);
  const paid = valid.filter((p) => p.kind === "paid");
  const ticks = [lo, (lo + hi) / 2, hi];
  const path = paid.map((p, i) => `${i ? "L" : "M"} ${x(p.date).toFixed(1)} ${y(p.price as number).toFixed(1)}`).join(" ");
  return (
    <div className="mt-2">
      <svg viewBox={`0 0 ${CW} ${CH}`} className="w-full overflow-visible" role="img" aria-label="Price history">
        {ticks.map((t) => (
          <g key={t}><line x1={PAD.l} x2={CW - PAD.r} y1={y(t)} y2={y(t)} style={{ stroke: "var(--line)" }} strokeDasharray="2 4" />
            <text x={PAD.l - 6} y={y(t) + 3} textAnchor="end" style={{ fill: "var(--muted)", fontSize: 10 }}>₹{Math.round(t)}</text></g>
        ))}
        <line x1={x(today)} x2={x(today)} y1={PAD.t} y2={CH - PAD.b} style={{ stroke: "var(--faint)" }} strokeDasharray="3 3" />
        <text x={x(today)} y={CH - 8} textAnchor="middle" style={{ fill: "var(--muted)", fontSize: 10 }}>today</text>
        {valid.filter((p) => p.kind === "quoted").map((p) => (
          <g key={p.ref}><rect x={x(p.date)} y={y(p.price as number) - 2} width={Math.max(4, x(p.until ?? p.date) - x(p.date))} height={4} rx={2} style={{ fill: "var(--violet)", opacity: 0.55 }} />
            <text x={x(p.date) + 2} y={y(p.price as number) - 6} style={{ fill: "var(--violet)", fontSize: 10 }}>{p.ref} ₹{p.price}</text></g>
        ))}
        <motion.path d={path} fill="none" style={{ stroke: "var(--accent)" }} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
                     initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }} />
        {paid.map((p, i) => (
          <motion.g key={p.ref} initial={{ opacity: 0, scale: 0.4 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.2 + i * 0.12 }} style={{ transformOrigin: `${x(p.date)}px ${y(p.price as number)}px` }}>
            <circle cx={x(p.date)} cy={y(p.price as number)} r={4.5} style={{ fill: "var(--accent)", stroke: "var(--panel)" }} strokeWidth={2}><title>{`${p.ref}: ₹${p.price} × ${p.qty ?? ""} from ${p.supplier ?? ""}`}</title></circle>
            <text x={x(p.date)} y={y(p.price as number) + 16} textAnchor="middle" style={{ fill: "var(--ink-soft)", fontSize: 10 }}>₹{p.price}</text>
          </motion.g>
        ))}
        {valid.filter((p) => p.kind === "notice").map((p) => (
          <g key={p.ref}><rect x={x(p.date) - 5} y={y(p.price as number) - 5} width={10} height={10} transform={`rotate(45 ${x(p.date)} ${y(p.price as number)})`} style={{ fill: "var(--danger)" }} />
            <text x={x(p.date) - 8} y={y(p.price as number) + 3} textAnchor="end" style={{ fill: "var(--danger)", fontSize: 10.5, fontWeight: 600 }}>notice ₹{p.price}</text></g>
        ))}
      </svg>
      <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-accent" /> paid</span>
        <span className="flex items-center gap-1"><span className="h-1 w-3 rounded bg-violet/60" /> quoted, while valid</span>
        <span className="flex items-center gap-1"><span className="h-2 w-2 rotate-45 bg-danger" /> supplier notice</span>
      </div>
    </div>
  );
}

/** The running balance from the stock ledger, with the reorder level. */
function BalanceChart({ moves, reorder, today }: { moves: Move[]; reorder: number | null; today: string }) {
  if (!moves.length) return <p className="mt-2 text-[13px] text-muted">No movements on record.</p>;
  const t = moves.map((m) => new Date(m.date).getTime()), now = new Date(today).getTime();
  const t0 = Math.min(...t), t1 = Math.max(now, ...t);
  const hi = Math.max(...moves.map((m) => m.balance), reorder ?? 0) * 1.1 || 1;
  const x = (ms: number) => PAD.l + ((ms - t0) / (t1 - t0 || 1)) * (CW - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - v / hi) * (CH - PAD.t - PAD.b);
  let d = `M ${x(t0)} ${y(0)}`;
  let prev = 0;
  moves.forEach((m, i) => { d += ` L ${x(t[i])} ${y(prev)} L ${x(t[i])} ${y(m.balance)}`; prev = m.balance; });
  d += ` L ${x(t1)} ${y(prev)}`;
  const area = `${d} L ${x(t1)} ${y(0)} Z`;
  return (
    <div className="mt-2 overflow-x-auto">
      <svg viewBox={`0 0 ${CW} ${CH}`} className="w-full" role="img" aria-label="Stock balance over time">
        <defs><linearGradient id="bal" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" style={{ stopColor: "var(--cyan)" }} stopOpacity="0.35" /><stop offset="100%" style={{ stopColor: "var(--cyan)" }} stopOpacity="0" /></linearGradient></defs>
        {[0, hi / 2, hi].map((v) => (
          <g key={v}><line x1={PAD.l} x2={CW - PAD.r} y1={y(v)} y2={y(v)} style={{ stroke: "var(--line)" }} strokeDasharray="2 4" />
            <text x={PAD.l - 6} y={y(v) + 3} textAnchor="end" style={{ fill: "var(--muted)", fontSize: 10 }}>{Math.round(v).toLocaleString("en-IN")}</text></g>
        ))}
        <motion.path d={area} style={{ fill: "url(#bal)" }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.8 }} />
        <motion.path d={d} fill="none" style={{ stroke: "var(--cyan)" }} strokeWidth={1.8} initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }} />
        {reorder ? <g><line x1={PAD.l} x2={CW - PAD.r} y1={y(reorder)} y2={y(reorder)} style={{ stroke: "var(--danger)" }} strokeDasharray="5 4" opacity={0.7} />
          <text x={CW - PAD.r} y={y(reorder) - 4} textAnchor="end" style={{ fill: "var(--danger)", fontSize: 10 }}>reorder level {reorder}</text></g> : null}
        <text x={PAD.l} y={CH - 8} style={{ fill: "var(--muted)", fontSize: 10 }}>{fmt(moves[0].date)}</text>
        <text x={CW - PAD.r} y={CH - 8} textAnchor="end" style={{ fill: "var(--muted)", fontSize: 10 }}>today</text>
      </svg>
    </div>
  );
}
