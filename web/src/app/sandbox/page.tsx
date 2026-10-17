"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import {
  Boxes, CopyPlus, Factory, FlaskConical, Loader2, Lock, PackageX, Play, Plus, Sparkles, Trash2, Truck, UserMinus, X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { PageTitle, Pill, Ticker } from "@/components/ui";
import { api, ApiError, inr } from "@/lib/api";

type Shock =
  | { kind: "part"; item: string; price?: number | null; lead_weeks?: number | null; eol?: boolean; label?: string }
  | { kind: "person"; person: string; start: string; end: string | null; label?: string }
  | { kind: "order"; order: string; factor: number; label?: string }
  | { kind: "supplier"; supplier: string; label?: string };
type Preset = { id: string; title: string; description: string; shocks: Shock[]; labels: string[] };
type Options = { parts: { id: string; name: string }[]; people: { id: string; name: string }[];
                 orders: { id: string; customer: string; qty: number; due: string }[]; suppliers: { id: string; name: string }[] };
type Finding = { key: string; severity: "high" | "medium" | "low"; title: string; detail: string; nodes: string[]; kind: string; only_in_combination: boolean };
type Metrics = { builds_at_risk: number; orders_exposed: number; value_at_risk: number; max_penalty: number; cost_increase: number;
                 tasks: number; people_stretched: number; knowledge_gaps: number };
type Result = { shocks: Shock[]; metrics: Metrics; each_alone: { label: string; metrics: Metrics; findings: number }[];
                findings: Finding[]; only_in_combination: number; copies: number; copy_ms: number; total_ms: number; assumptions: string[] };

const KIND = {
  part: { icon: PackageX, label: "Part change", tone: "text-warn" },
  person: { icon: UserMinus, label: "Person away", tone: "text-violet" },
  order: { icon: Boxes, label: "Order change", tone: "text-accent" },
  supplier: { icon: Truck, label: "Supplier stops", tone: "text-danger" },
} as const;

const METRICS: { key: keyof Metrics; label: string; money?: boolean }[] = [
  { key: "builds_at_risk", label: "Builds at risk" },
  { key: "orders_exposed", label: "Orders exposed" },
  { key: "value_at_risk", label: "Order value exposed", money: true },
  { key: "max_penalty", label: "Penalty exposure", money: true },
  { key: "cost_increase", label: "Cost increase", money: true },
  { key: "tasks", label: "Tasks the change needs" },
  { key: "people_stretched", label: "People stretched" },
  { key: "knowledge_gaps", label: "Knowledge gaps" },
];

const severity = { high: "danger", medium: "warn", low: "neutral" } as const;
const href = (id: string) => (id.startsWith("P-") ? `/people?id=${id}` : `/explore?id=${encodeURIComponent(id)}`);

export default function Sandbox() {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [opts, setOpts] = useState<Options | null>(null);
  const [shocks, setShocks] = useState<Shock[]>([]);
  const [adding, setAdding] = useState<Shock["kind"] | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);

  useEffect(() => {
    api<Preset[]>("/api/sandbox/presets").then(setPresets).catch((e) => {
      if (e instanceof ApiError && e.status === 403) setBlocked(String((e.body as { detail?: string })?.detail ?? "Not available"));
    });
    api<Options>("/api/sandbox/options").then(setOpts).catch(() => {});
  }, []);

  async function run(list = shocks) {
    if (!list.length) return;
    setBusy(true); setError(null);
    try {
      setResult(await api<Result>("/api/sandbox", { method: "POST", body: JSON.stringify({ shocks: list }) }));
    } catch (e) {
      setError(e instanceof ApiError ? String((e.body as { detail?: string })?.detail ?? e.message) : (e as Error).message);
    } finally { setBusy(false); }
  }

  function preset(p: Preset) {
    const list = p.shocks.map((s, i) => ({ ...s, label: p.labels[i] }));
    setShocks(list);
    run(list);
  }

  if (blocked) {
    return (
      <div className="space-y-4">
        <PageTitle>Try it on a <em>copy</em> of Flyvi</PageTitle>
        <div className="card flex items-center gap-3 p-5 text-sm text-muted"><Lock size={16} /> {blocked}. Switch to a director or a member of the leadership team to try it.</div>
      </div>
    );
  }

  const combined = result?.findings.filter((f) => f.only_in_combination) ?? [];
  const rest = result?.findings.filter((f) => !f.only_in_combination) ?? [];

  return (
    <div className="space-y-5">
      <div>
        <PageTitle>Try it on a <em>copy</em> of Flyvi</PageTitle>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Every scenario runs on a fresh copy of the whole company graph, made by FalkorDB in about a tenth of a second, then thrown away.
          Each change is also tried alone, so Neura1 can show what only goes wrong when they happen together.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[380px_minmax(0,1fr)]">
        <div className="space-y-4">
          <section data-tour="sandbox" className="card p-4">
            <div className="mb-2 text-[12px] font-medium text-faint">Scenarios</div>
            <div className="grid gap-2">
              {presets.map((p) => (
                <button key={p.id} onClick={() => preset(p)} disabled={busy}
                        className="lift group rounded-xl border border-line bg-elev/60 px-3 py-2.5 text-left transition hover:border-accent/40 hover:bg-accent/[0.06] disabled:opacity-60">
                  <div className="flex items-center gap-2 text-[13.5px] font-semibold">
                    <FlaskConical size={14} className="text-accent" />{p.title}
                    <Play size={12} className="ml-auto text-faint opacity-0 transition group-hover:opacity-100" />
                  </div>
                  <div className="mt-0.5 text-[12px] leading-snug text-muted">{p.description}</div>
                </button>
              ))}
            </div>
          </section>

          <section className="card p-4">
            <div className="mb-2 flex items-center text-[12px] font-medium text-faint">Changes to try
              {shocks.length > 0 && <button onClick={() => { setShocks([]); setResult(null); }} className="ml-auto text-faint hover:text-ink">Clear</button>}</div>
            <ul className="space-y-1.5">
              <AnimatePresence initial={false}>
                {shocks.map((s, i) => {
                  const K = KIND[s.kind];
                  return (
                    <motion.li key={`${s.kind}-${i}-${s.label}`} layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: -10 }}
                               className="flex items-center gap-2.5 rounded-xl border border-line bg-panel px-3 py-2 text-[13px]">
                      <K.icon size={15} className={K.tone} />
                      <span className="min-w-0 flex-1 truncate">{s.label ?? K.label}</span>
                      <button onClick={() => setShocks((x) => x.filter((_, j) => j !== i))} aria-label="Remove" className="rounded p-0.5 text-faint hover:text-danger"><Trash2 size={13} /></button>
                    </motion.li>
                  );
                })}
              </AnimatePresence>
              {!shocks.length && <li className="rounded-xl border border-dashed border-line px-3 py-3 text-[12.5px] text-muted">Pick a scenario above, or add changes below.</li>}
            </ul>
            <div className="mt-3 grid grid-cols-4 gap-1.5">
              {(Object.keys(KIND) as Shock["kind"][]).map((k) => {
                const K = KIND[k];
                return (
                  <button key={k} onClick={() => setAdding(adding === k ? null : k)} aria-pressed={adding === k}
                          className={`flex flex-col items-center gap-1 rounded-xl border px-1 py-2 text-[11px] transition ${adding === k ? "border-accent/50 bg-accent/10 text-ink" : "border-line text-muted hover:border-line2 hover:text-ink"}`}>
                    <K.icon size={15} className={K.tone} />{K.label.split(" ")[0]}
                  </button>
                );
              })}
            </div>
            <AnimatePresence>
              {adding && opts && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                  <AddShock kind={adding} opts={opts} onAdd={(s) => { setShocks((x) => [...x, s]); setAdding(null); }} onCancel={() => setAdding(null)} />
                </motion.div>
              )}
            </AnimatePresence>
            <button onClick={() => run()} disabled={busy || !shocks.length}
                    className="press mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-[13.5px] font-medium text-accent-ink transition hover:bg-accent-hover disabled:opacity-40">
              {busy ? <Loader2 size={15} className="animate-spin" /> : <CopyPlus size={15} />} {busy ? "Copying Flyvi and running…" : "Run on a copy of Flyvi"}
            </button>
            {error && <div className="mt-2 text-[12px] text-warn">{error}</div>}
          </section>
        </div>

        <div className="min-w-0 space-y-4">
          {!result && !busy && (
            <div className="card grid min-h-[420px] place-items-center p-8 text-center">
              <div className="max-w-md space-y-3">
                <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-accent/12 text-accent"><FlaskConical size={24} /></span>
                <div className="text-[17px] font-semibold tracking-tight">Nothing here touches the real company</div>
                <p className="text-[13px] text-muted">Each run copies the graph, applies your changes to the copy, runs the same engines Neura1 uses every day, and discards the copy. Start with &ldquo;The perfect storm&rdquo;.</p>
              </div>
            </div>
          )}
          {busy && !result && (
            <div className="card grid min-h-[420px] place-items-center text-muted"><div className="flex items-center gap-2 text-sm"><Loader2 size={16} className="animate-spin" /> Copying the company graph…</div></div>
          )}
          {result && (
            <motion.div key={result.total_ms} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: busy ? 0 : 0 }} className={`space-y-4 transition-opacity ${busy ? "opacity-50" : ""}`}>
              <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
                <Pill tone="accent" dot>Copied in {result.copy_ms.toFixed(0)} ms</Pill>
                <Pill>{result.copies} {result.copies === 1 ? "copy" : "copies"}: {result.shocks.length > 1 ? "each change alone, then together" : "one change"}</Pill>
                <Pill>{(result.total_ms / 1000).toFixed(1)} s in all</Pill>
                <Pill tone="success">Copies discarded · real graph untouched</Pill>
              </div>

              <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
                {METRICS.map((m) => {
                  const v = result.metrics[m.key];
                  return (
                    <div key={m.key} className={`card p-3.5 ${v ? "" : "opacity-60"}`}>
                      <div className="text-[11.5px] text-muted">{m.label}</div>
                      <div className={`mt-1 text-[22px] font-semibold tracking-tight ${v && (m.key === "builds_at_risk" || m.key === "orders_exposed") ? "text-danger" : ""}`}>
                        {m.money ? <Ticker value={v} format={(n) => inr(Math.round(n))} /> : <Ticker value={v} />}
                      </div>
                    </div>
                  );
                })}
              </div>

              {combined.length > 0 && (
                <section className="relative overflow-hidden rounded-[22px] border border-accent/35 bg-gradient-to-br from-accent/[0.10] via-violet/[0.06] to-transparent p-5">
                  <div className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-accent"><Sparkles size={13} /> Only when these happen together</div>
                  <p className="mt-1 text-[13px] text-muted">None of these appear when each change is tried alone. No single report, meeting or spreadsheet would have shown them.</p>
                  <div className="mt-3 space-y-2">
                    {combined.map((f, i) => <FindingRow key={f.key} f={f} i={i} strong />)}
                  </div>
                </section>
              )}

              {result.each_alone.length > 1 && (
                <section className="card p-4">
                  <div className="mb-2 text-[12px] font-medium text-faint">Each change alone, then together</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-[13px]">
                      <thead><tr className="text-left text-[11.5px] text-muted"><th className="py-1 font-medium">Change</th><th className="font-medium">Builds at risk</th><th className="font-medium">Orders exposed</th><th className="font-medium">Findings</th></tr></thead>
                      <tbody>
                        {result.each_alone.map((a) => (
                          <tr key={a.label} className="border-t border-line"><td className="py-1.5 pr-3">{a.label}</td><td className="num">{a.metrics.builds_at_risk}</td><td className="num">{a.metrics.orders_exposed}</td><td className="num">{a.findings}</td></tr>
                        ))}
                        <tr className="border-t border-line font-semibold"><td className="py-1.5">All together</td><td className="num">{result.metrics.builds_at_risk}</td><td className="num">{result.metrics.orders_exposed}</td><td className="num">{result.findings.length}</td></tr>
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              <section className="card p-4">
                <div className="mb-2 text-[12px] font-medium text-faint">Everything that breaks</div>
                <div className="space-y-2">{rest.map((f, i) => <FindingRow key={f.key} f={f} i={i} />)}</div>
                {!result.findings.length && <div className="py-6 text-center text-[13px] text-muted">Nothing breaks in this scenario.</div>}
              </section>
              <ul className="space-y-0.5 px-1 text-[11.5px] text-faint">{result.assumptions.map((a) => <li key={a}>· {a}</li>)}</ul>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}

function FindingRow({ f, i, strong = false }: { f: Finding; i: number; strong?: boolean }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.04, 0.4), duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                className={`rounded-xl border px-3.5 py-2.5 ${strong ? "border-accent/30 bg-panel/80" : "border-line bg-elev/40"}`}>
      <div className="flex items-start gap-2">
        <Pill tone={severity[f.severity]}>{f.severity}</Pill>
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] font-medium">{f.title}</div>
          <div className="mt-0.5 text-[12.5px] leading-relaxed text-muted">{f.detail}</div>
          {f.nodes.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {f.nodes.slice(0, 6).map((n) => <Link key={n} href={href(n)} className="rounded-md bg-elev px-1.5 py-0.5 font-mono text-[11px] text-ink-soft transition hover:bg-accent/15 hover:text-ink">{n}</Link>)}
            </div>
          )}
        </div>
        {f.kind === "build" && <Factory size={14} className="mt-0.5 shrink-0 text-faint" />}
      </div>
    </motion.div>
  );
}

function AddShock({ kind, opts, onAdd, onCancel }: { kind: Shock["kind"]; opts: Options; onAdd: (s: Shock) => void; onCancel: () => void }) {
  const [a, setA] = useState("");
  const [price, setPrice] = useState("");
  const [lead, setLead] = useState("");
  const [eol, setEol] = useState(false);
  const [start, setStart] = useState(() => new Date(Date.now() + 7 * 864e5).toISOString().slice(0, 10));
  const [end, setEnd] = useState("");
  const [leaves, setLeaves] = useState(false);
  const [factor, setFactor] = useState(2);
  const field = "w-full rounded-lg border border-line px-2.5 py-1.5 text-[13px]";
  const name = (list: { id: string; name?: string; customer?: string }[], id: string) => list.find((x) => x.id === id)?.name ?? list.find((x) => x.id === id)?.customer ?? id;

  function add() {
    if (!a) return;
    if (kind === "part") {
      if (!eol && !price && !lead) return;
      onAdd({ kind, item: a, price: price ? Number(price) : null, lead_weeks: lead ? Number(lead) : null, eol,
              label: eol ? `${a} goes end of life` : `${a}: ${[price && `price ₹${price}`, lead && `lead time ${lead} weeks`].filter(Boolean).join(", ")}` });
    } else if (kind === "person") {
      if (!leaves && !end) return;
      onAdd({ kind, person: a, start, end: leaves ? null : end, label: leaves ? `${name(opts.people, a)} leaves Flyvi from ${start}` : `${name(opts.people, a)} is away ${start} to ${end}` });
    } else if (kind === "order") {
      onAdd({ kind, order: a, factor, label: `${a} × ${factor}` });
    } else {
      onAdd({ kind, supplier: a, label: `${name(opts.suppliers, a)} stops supplying` });
    }
  }

  return (
    <div className="mt-3 space-y-2 rounded-xl border border-line bg-elev/50 p-3">
      <select value={a} onChange={(e) => setA(e.target.value)} className={field} aria-label="Choose">
        <option value="">{kind === "part" ? "Choose a part…" : kind === "person" ? "Choose a person…" : kind === "order" ? "Choose an order…" : "Choose a supplier…"}</option>
        {kind === "part" && opts.parts.map((p) => <option key={p.id} value={p.id}>{p.id} · {p.name}</option>)}
        {kind === "person" && opts.people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        {kind === "order" && opts.orders.map((o) => <option key={o.id} value={o.id}>{o.id} · {o.customer} · {o.qty} due {o.due}</option>)}
        {kind === "supplier" && opts.suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      {kind === "part" && (
        <div className="grid grid-cols-2 gap-2">
          <input value={price} onChange={(e) => setPrice(e.target.value.replace(/[^\d.]/g, ""))} placeholder="New price ₹" disabled={eol} className={field} />
          <input value={lead} onChange={(e) => setLead(e.target.value.replace(/\D/g, ""))} placeholder="Lead weeks" disabled={eol} className={field} />
          <label className="col-span-2 flex items-center gap-2 text-[12.5px] text-muted"><input type="checkbox" checked={eol} onChange={(e) => setEol(e.target.checked)} /> End of life: no further supply</label>
        </div>
      )}
      {kind === "person" && (
        <div className="grid grid-cols-2 gap-2">
          <label className="text-[11.5px] text-muted">From<input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={field} /></label>
          <label className="text-[11.5px] text-muted">Until<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} disabled={leaves} className={field} /></label>
          <label className="col-span-2 flex items-center gap-2 text-[12.5px] text-muted"><input type="checkbox" checked={leaves} onChange={(e) => setLeaves(e.target.checked)} /> Leaves Flyvi</label>
        </div>
      )}
      {kind === "order" && (
        <label className="block text-[12px] text-muted">Scale the order: <b className="text-ink">× {factor}</b>
          <input type="range" min={0.5} max={3} step={0.25} value={factor} onChange={(e) => setFactor(Number(e.target.value))} className="mt-1 w-full accent-[var(--accent)]" />
        </label>
      )}
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="flex items-center gap-1 rounded-lg px-2.5 py-1 text-[12.5px] text-muted hover:bg-elev"><X size={13} /> Cancel</button>
        <button onClick={add} className="flex items-center gap-1 rounded-lg bg-ink px-2.5 py-1 text-[12.5px] font-medium text-[var(--bg)] hover:opacity-90"><Plus size={13} /> Add</button>
      </div>
    </div>
  );
}
