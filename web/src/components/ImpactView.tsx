"use client";

import { AlertTriangle, CheckCircle2, CircleHelp, ClipboardCopy, Download, FileText, ShieldX } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import ImpactGraph from "@/components/ImpactGraph";
import { api, ApiError, inr, type Alternate, type ImpactReport, type Unresolved } from "@/lib/api";

type Props = { source?: string; item?: string; price?: string; lead?: string; asOf?: string };
type Open = { chunk: string; quote?: string } | null;

const LENSES = ["Engineering", "Procurement", "Production", "Sales", "Support", "Management", "How it was computed"] as const;
type Lens = (typeof LENSES)[number];

export default function ImpactView({ source, item, price, lead, asOf }: Props) {
  const [report, setReport] = useState<ImpactReport | null>(null);
  const [unresolved, setUnresolved] = useState<Unresolved | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Open>(null);
  const [lens, setLens] = useState<Lens>("Engineering");

  const load = useCallback(() => {
    const request = source
      ? api<ImpactReport>(`/api/impact/notice?source_id=${encodeURIComponent(source)}${asOf ? `&as_of=${asOf}` : ""}`, { method: "POST" })
      : api<ImpactReport | Unresolved>("/api/impact", {
          method: "POST",
          body: JSON.stringify({ item, new_unit_price: price || null, lead_weeks: lead ? Number(lead) : null, currency: "INR", as_of: asOf }),
        });
    return request.then(
      (r) => {
        setError(null);
        if (r.status === "unresolved") setUnresolved(r as Unresolved);
        else setReport(r as ImpactReport);
      },
      (e) => setError(e instanceof ApiError && e.status === 503
        ? "The company graph is unavailable, so no impact analysis can be given."
        : (e as Error).message),
    );
  }, [source, item, price, lead, asOf]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <div className="card p-6 text-danger">{error}</div>;
  if (unresolved) {
    const cands = unresolved.candidates as { id: string; name: string; mpn: string }[];
    return (
      <div className="card p-6">
        <div className="font-medium">No part in the company graph is exactly “{unresolved.item}”.</div>
        {cands.length ? (
          <>
            <div className="mt-1 text-sm text-muted">Did the notice mean one of these? Neura1 will not pick for you.</div>
            <ul className="mt-3 space-y-1 text-sm">
              {cands.map((c) => (
                <li key={c.id}>
                  <a className="text-accent hover:underline"
                     href={`/impact?${new URLSearchParams({ item: c.id, ...(price && { price }), ...(lead && { lead }) })}`}>
                    {c.id}
                  </a>{" "}
                  <span className="text-muted">{c.name}{c.mpn ? ` · ${c.mpn}` : ""}</span>
                </li>
              ))}
            </ul>
          </>
        ) : <div className="mt-1 text-sm text-muted">Nothing similar either. Import the part first.</div>}
      </div>
    );
  }
  if (!report) return <div className="p-6 text-muted">Tracing through the company graph…</div>;

  const r = report;
  const applicable = r.where_used.filter((u) => u.applicable);
  const excluded = r.where_used.filter((u) => !u.applicable);
  const atRisk = r.builds.filter((b) => b.at_risk);
  const orders = r.builds.flatMap((b) => b.orders);
  const owners = new Set(r.actions.map((a) => a.owner).filter(Boolean));
  const baseline = r.cost ? Number(r.cost.baseline_unit_price) : null;
  const baselineQuote = r.quotes.find((q) => q.id === r.cost?.baseline_quote);

  return (
    <div className="space-y-5">
      {/* The change */}
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted">
            {r.change.source_id ? "Supplier notice" : "What-if"} · as of {r.change.as_of}
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">
            {r.part.id} <span className="font-normal text-muted">{r.part.name}</span>
          </h1>
          <div className="mt-2 flex flex-wrap gap-2 text-sm">
            {r.change.new_unit_price !== null && (
              <Chip>Price {inr(baseline)} → <b>{inr(r.change.new_unit_price)}</b>
                {baseline ? ` (${(((Number(r.change.new_unit_price) - baseline) / baseline) * 100).toFixed(0)}%)` : ""}</Chip>
            )}
            {r.change.lead_weeks !== null && (
              <Chip>Lead time {baselineQuote?.lead_weeks ?? "?"} → <b>{r.change.lead_weeks} weeks</b></Chip>
            )}
            {r.change.effective_date && <Chip>Effective {r.change.effective_date}</Chip>}
            <Chip>Owner {r.part.owner ?? "unassigned"}</Chip>
          </div>
        </div>
      </section>

      {r.changes_since_approval?.length > 0 && (
        <section className="rounded-xl border border-accent/40 bg-accent/12 p-4 text-sm">
          <div className="font-medium text-accent">Changed since this was approved ({r.investigation?.created_at.slice(0, 10)})</div>
          <ul className="mt-1 list-disc pl-5">
            {r.changes_since_approval.map((c) => <li key={c}>{c}</li>)}
          </ul>
        </section>
      )}

      {/* What the company already knows about alternates */}
      <section className="space-y-2">
        {r.alternates.map((a) => <AlternateBanner key={a.id} a={a} part={r.part.id} onOpen={setOpen} />)}
      </section>

      {/* Headline numbers */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Product revisions affected" value={applicable.length}
              note={`${excluded.length} excluded (${excluded.map((e) => `${e.revision} ${e.status}`).join(", ")})`} />
        <Stat label="Builds at risk" value={`${atRisk.length} of ${r.builds.length}`}
              note={r.builds[0]?.supply_eta_if_ordered_today ? `new supply ~${r.builds[0].supply_eta_if_ordered_today}` : ""} />
        <Stat label="Customer orders exposed" value={orders.length}
              note={`${orders.filter((o) => o.penalty).length} with a penalty clause`} warn={orders.some((o) => o.penalty)} />
        <Stat label="Cost increase" value={r.cost ? inr(r.cost.total_delta) : "unknown"}
              note={r.cost ? r.cost.formula : r.cost_error ?? ""} />
        <Stat label="People to involve" value={owners.size} note={`${r.actions.length} tasks under HB-ENG-04`} />
      </section>

      {/* Graph + actions */}
      <section className="grid gap-4 lg:grid-cols-[1fr_400px]">
        <div className="card h-[560px] overflow-hidden">
          <ImpactGraph
            nodes={r.graph.nodes}
            edges={r.graph.edges}
            onSelect={(n) => {
              const d = r.decisions.find((x) => x.id === n.id);
              if (d?.evidence[0]?.chunk) setOpen({ chunk: d.evidence[0].chunk, quote: d.evidence[0].quote });
            }}
          />
        </div>
        <ActionsPanel report={r} onDone={load} onOpen={setOpen} />
      </section>

      {/* Department lenses over the same graph */}
      <section className="card">
        <div className="flex gap-1 overflow-x-auto border-b border-line px-2 pt-2">
          {LENSES.map((l) => (
            <button key={l} onClick={() => setLens(l)}
                    className={`whitespace-nowrap rounded-t-md px-3 py-2 text-sm ${lens === l ? "border border-b-0 border-line bg-panel font-medium" : "text-muted hover:text-ink"}`}>
              {l}
            </button>
          ))}
        </div>
        <div className="p-4 text-sm">{renderLens(lens, r, setOpen)}</div>
      </section>

      {open && <EvidenceDrawer key={open.chunk} chunk={open.chunk} quote={open.quote} onClose={() => setOpen(null)} />}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full border border-line bg-panel px-3 py-1">{children}</span>;
}

function Stat({ label, value, note, warn }: { label: string; value: React.ReactNode; note?: string; warn?: boolean }) {
  return (
    <div className={`card p-3 ${warn ? "border-warn/40" : ""}`}>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
      {note && <div className="mt-1 truncate text-xs text-muted" title={note}>{note}</div>}
    </div>
  );
}

function AlternateBanner({ a, part, onOpen }: { a: Alternate; part: string; onOpen: (o: Open) => void }) {
  const price = a.quotes[0] ? `${inr(a.quotes[0].unit_price)} from ${a.quotes[0].supplier}` : "no quote on file";
  if (a.status === "rejected") {
    const d = a.decisions.find((x) => x.outcome === "rejected")!;
    return (
      <div className="rounded-xl border border-danger/40 bg-danger/10 p-4">
        <div className="flex items-start gap-3">
          <ShieldX className="mt-0.5 shrink-0 text-danger" size={20} />
          <div className="min-w-0 flex-1">
            <div className="font-medium text-danger">
              Do not switch to {a.id}. It was rejected as a substitute for {part} ({d.id})
            </div>
            <div className="mt-1 text-sm">
              {d.reason ?? d.summary}. Decided by <b>{d.decided_by ?? "unknown"}</b>
              {d.decided_at ? ` on ${d.decided_at}` : ""}
              {d.applies_to.length ? `, applies to ${d.applies_to.join(", ")}` : ""}. It is cheaper ({price}) and listed as
              pin-compatible, which is why it keeps coming up.
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {d.evidence.map((e) => (
                <button key={e.chunk} onClick={() => onOpen({ chunk: e.chunk, quote: e.quote })}
                        className="flex items-center gap-1.5 rounded-md border border-danger/30 bg-elev px-2 py-1 text-xs hover:border-danger">
                  <FileText size={12} /> {e.title}{e.page ? ` p.${e.page}` : ""}{e.author ? ` · ${e.author}` : ""}
                </button>
              ))}
            </div>
            <div className="mt-2 text-xs text-muted">
              Found by {d.extracted_by ?? "a model"} in Voltline&apos;s chats and tickets. Every quote was verified word for word
              against the source before it entered the graph. A person can confirm or overturn it.
            </div>
          </div>
        </div>
      </div>
    );
  }
  if (a.status === "pending_review") {
    const d = a.decisions[0];
    return (
      <div className="rounded-xl border border-warn/40 bg-warn/10 p-4 text-sm">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 shrink-0 text-warn" size={20} />
          <div>
            <div className="font-medium text-warn">{a.id}: candidate, pending engineering approval</div>
            <div className="mt-1">{d?.summary}. {price}. A chat message or bench result cannot approve a part (HB-ENG-04 clause 2).</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {d?.evidence.map((e) => (
                <button key={e.chunk} onClick={() => onOpen({ chunk: e.chunk, quote: e.quote })}
                        className="flex items-center gap-1.5 rounded-md border border-warn/30 bg-elev px-2 py-1 text-xs">
                  <FileText size={12} /> {e.title}{e.author ? ` · ${e.author}` : ""}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }
  if (a.status === "approved") {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-accent/40 bg-accent/12 p-3 text-sm">
        <CheckCircle2 className="text-accent" size={18} /> {a.id} is an approved alternate. {price}.
      </div>
    );
  }
  return (
    <div className="flex items-start gap-3 rounded-xl border border-line bg-panel p-3 text-sm">
      <CircleHelp className="mt-0.5 shrink-0 text-muted" size={18} />
      <div>
        <b>{a.id}</b> ({a.manufacturer}) is listed as an alternate by {a.basis.replace("_", " ")}, {price}. No
        qualification evidence is recorded, so it needs engineering review before use.
      </div>
    </div>
  );
}

function briefText(r: ImpactReport): string {
  const byOwner = new Map<string, string[]>();
  r.actions.forEach((a) => byOwner.set(a.owner ?? "Unassigned", [...(byOwner.get(a.owner ?? "Unassigned") ?? []), a.title]));
  const orders = r.builds.flatMap((b) => b.orders);
  const lines = [
    `*${r.part.id} change*: ${r.change.new_unit_price ? `price ${inr(r.cost?.baseline_unit_price)} → ${inr(r.change.new_unit_price)}` : ""}${r.change.lead_weeks ? `, lead time ${r.change.lead_weeks} weeks` : ""}`,
    `Affects ${r.where_used.filter((u) => u.applicable).map((u) => u.revision).join(", ")}; ${r.builds.filter((b) => b.at_risk).length} builds at risk; orders ${orders.map((o) => `${o.order} (${o.customer}${o.penalty ? ", penalty clause" : ""})`).join(", ")}.`,
    r.cost ? `Cost increase ${inr(r.cost.total_delta)} (${r.cost.formula}).` : "",
    ...r.alternates.filter((a) => a.status === "rejected").map((a) => `Do not use ${a.id}: ${a.decisions[0]?.reason ?? "previously rejected"} (${a.decisions[0]?.id}).`),
    "",
    ...[...byOwner].flatMap(([o, ts]) => [`*${o}*`, ...ts.map((t) => `• ${t}`)]),
  ];
  return lines.filter((l, i) => l || i > 0).join("\n");
}

function downloadCsv(r: ImpactReport) {
  const esc = (v: string) => `"${v.replaceAll('"', '""')}"`;
  const rows = [["owner", "task", "why", "sources"], ...r.actions.map((a) => [a.owner ?? "", a.title, a.why, a.cites.join(" ")])];
  const blob = new Blob([rows.map((x) => x.map(esc).join(",")).join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${r.part.id}-tasks.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function ActionsPanel({ report: r, onDone, onOpen }: { report: ImpactReport; onDone: () => void; onOpen: (o: Open) => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const inv = r.investigation;

  async function approve() {
    let name = "", pass = "";
    try {
      name = localStorage.getItem("neura1-reviewer") ?? "";
      pass = localStorage.getItem("neura1-passcode") ?? "";
    } catch {}
    name = name || prompt("Your name (recorded as approver)") || "";
    pass = pass || prompt("Demo passcode") || "";
    if (!name || !pass) return;
    try {
      localStorage.setItem("neura1-reviewer", name);
      localStorage.setItem("neura1-passcode", pass);
    } catch {}
    setBusy(true);
    try {
      const res = await api<{ created: string[]; already_existed: string[] }>(`/api/actions/approve?as_of=${r.change.as_of}`, {
        method: "POST", write: true,
        body: JSON.stringify({ item_id: r.part.id, source_id: r.change.source_id, approved_by: name,
                               new_unit_price: r.change.new_unit_price === null ? null : String(r.change.new_unit_price),
                               lead_weeks: r.change.lead_weeks, currency: r.change.currency }),
      });
      setMsg(`${res.created.length} tasks created, ${res.already_existed.length} already existed.`);
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        try { localStorage.removeItem("neura1-passcode"); } catch {}
      }
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card flex h-[560px] flex-col">
      <div className="border-b border-line p-4">
        <div className="font-medium">Who needs to do what</div>
        {inv ? (
          <div className="mt-1 text-xs text-accent">
            Already investigated on {inv.created_at.replace("T", " ").slice(0, 16)} UTC, approved by {inv.approved_by} ({inv.id}).
          </div>
        ) : (
          <div className="mt-1 text-xs text-muted">Proposed from the change policy and owners recorded in the graph.</div>
        )}
      </div>
      <ol className="flex-1 space-y-2 overflow-y-auto p-4">
        {r.actions.map((a, i) => {
          const saved = inv?.actions.find((x) => x.title === a.title);
          return (
            <li key={i} className="rounded-lg border border-line p-3 text-sm">
              <div className="flex items-start justify-between gap-2">
                <span className="font-medium">{a.title}</span>
                {saved && <span className="shrink-0 rounded bg-accent/12 px-1.5 py-0.5 text-[10px] text-accent">{saved.status}</span>}
              </div>
              <div className="mt-1 text-xs text-muted">{a.owner ?? "No owner recorded"} · {a.why}</div>
              {a.cites.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {a.cites.map((c) => (
                    <button key={c} onClick={() => onOpen({ chunk: c })}
                            className="rounded bg-bg px-1.5 py-0.5 font-mono text-[10px] text-muted hover:text-ink">
                      {c.split("/").pop()?.split("#")[0]}
                    </button>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <div className="border-t border-line p-4">
        <button onClick={approve} disabled={busy}
                className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
          {inv ? "Approve again (no duplicates)" : "Approve and assign tasks"}
        </button>
        <div className="mt-2 flex gap-2">
          <button onClick={() => { navigator.clipboard.writeText(briefText(r)); setMsg("Copied. Paste it into Slack, Teams, WhatsApp or email."); }}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs hover:border-ink">
            <ClipboardCopy size={13} /> Copy as message
          </button>
          <button onClick={() => downloadCsv(r)}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs hover:border-ink">
            <Download size={13} /> Tasks CSV
          </button>
        </div>
        {msg && <div className="mt-2 text-xs text-muted">{msg}</div>}
      </div>
    </div>
  );
}

function Table({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-muted">
          <tr>{head.map((h) => <th key={h} className="border-b border-line py-2 pr-4 font-normal">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line/60 last:border-0">
              {r.map((c, j) => <td key={j} className="py-2 pr-4 align-top">{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderLens(lens: Lens, r: ImpactReport, onOpen: (o: Open) => void) {
  const c = r.cost;
  switch (lens) {
    case "Engineering":
      return (
        <div className="space-y-5">
          <div>
            <h3 className="mb-2 font-medium">Where {r.part.id} is used</h3>
            <Table head={["Revision", "Status", "Qty per unit", "Paths (reference designators)"]}
                   rows={r.where_used.map((u) => [
                     <span key="r" className="font-mono">{u.revision}</span>,
                     u.applicable ? u.status : <span key="s" className="text-muted">{u.status} (excluded)</span>,
                     u.applicable ? u.qty_per_unit : <span key="q" className="text-muted">{u.qty_if_built} if built</span>,
                     <div key="p" className="space-y-0.5 font-mono text-xs">
                       {u.paths.map((p, i) => <div key={i}>{p.nodes.join(" → ")} <span className="text-muted">[{p.refdes.join(", ")}] ×{p.qty}</span></div>)}
                     </div>,
                   ])} />
          </div>
          <div>
            <h3 className="mb-2 font-medium">Firmware and test dependencies</h3>
            <Table head={["Item", "Why it depends on the part", "Owner", "Evidence"]}
                   rows={r.dependents.map((d) => [
                     d.name, d.note, `${d.owner ?? "—"}${d.team ? ` (${d.team})` : ""}`,
                     <div key="e" className="flex flex-wrap gap-1">
                       {d.evidence.filter((e) => e.chunk).map((e) => (
                         <button key={e.chunk} onClick={() => onOpen({ chunk: e.chunk })}
                                 className="rounded bg-bg px-1.5 py-0.5 text-xs hover:underline">{e.title.split(":")[0]}</button>
                       ))}
                     </div>,
                   ])} />
          </div>
        </div>
      );
    case "Procurement":
      return (
        <div className="space-y-5">
          <Table head={["Quote", "Part", "Supplier", "Unit price", "MOQ", "Lead", "Valid", "Used?"]}
                 rows={[...r.quotes.map((q) => ({ ...q, part: r.part.id })),
                        ...r.alternates.flatMap((a) => a.quotes.map((q) => ({ ...q, part: a.id })))].map((q) => [
                   <span key="i" className="font-mono">{q.id}</span>, q.part, q.supplier, inr(q.unit_price), q.moq,
                   `${q.lead_weeks} wk`, `${q.valid_from} → ${q.valid_until}`,
                   q.id === c?.baseline_quote ? <b key="b">baseline</b>
                     : q.valid_until < r.change.as_of ? <span key="x" className="text-danger">expired</span> : "",
                 ])} />
          <div className="text-muted">
            Stock: {r.part.on_hand} on hand, {r.part.allocated} allocated, {c?.free_stock ?? "?"} free. Net need after free
            stock: <b className="text-ink">{c?.net_need}</b> (purchase {c?.purchase_qty}).
          </div>
        </div>
      );
    case "Production":
      return (
        <Table head={["Build", "Revision", "Planned", "Parts needed", "From free stock", "Shortfall", "Supply if ordered today", "Planner"]}
               rows={r.builds.map((b) => [
                 <span key="b" className="font-mono">{b.build}</span>, b.revision, b.planned_date,
                 `${b.build_qty} × ${b.parts_needed / b.build_qty} = ${b.parts_needed}`, b.from_stock,
                 b.shortfall ? <b key="s" className="text-warn">{b.shortfall}</b> : 0,
                 b.supply_eta_if_ordered_today ?? "—", b.planner ?? "—",
               ])} />
      );
    case "Sales":
      return (
        <Table head={["Order", "Customer", "Qty", "Due", "Via build", "Contract note", "Account manager"]}
               rows={r.builds.flatMap((b) => b.orders.map((o) => [
                 <span key="o" className="font-mono">{o.order}</span>, o.customer, o.qty, o.due, b.build,
                 o.penalty ? <span key="p" className="text-warn">{o.penalty}</span> : "—", o.account_manager ?? "—",
               ]))} />
      );
    case "Support":
      return r.field_units.length ? (
        <div className="space-y-3">
          <Table head={["Shipment", "Customer", "Revision", "Units", "Shipped"]}
                 rows={r.field_units.map((f) => [f.shipment, f.customer, `${f.revision} (${f.status})`, f.qty, f.shipped_on])} />
          <div className="text-muted">These units contain {r.part.id}. They are not affected by the price change, but spares and
            repairs will need the new lead time.</div>
        </div>
      ) : <div className="text-muted">No shipped units contain this part.</div>;
    case "Management": {
      const orders = r.builds.flatMap((b) => b.orders);
      const rejected = r.alternates.filter((a) => a.status === "rejected");
      return (
        <div className="max-w-3xl space-y-3 leading-relaxed">
          <p>
            <b>{r.part.id}</b> ({r.part.name}) changes{r.change.new_unit_price ? ` to ${inr(r.change.new_unit_price)} per unit` : ""}
            {r.change.lead_weeks ? ` with a ${r.change.lead_weeks}-week lead time` : ""}. It is used in{" "}
            {r.where_used.filter((u) => u.applicable).map((u) => `${u.revision} (${u.qty_per_unit}/unit)`).join(" and ")}.
          </p>
          <p>
            {r.builds.filter((b) => b.at_risk).length} planned builds cannot be covered from free stock before new supply could
            arrive. They feed {orders.length} customer orders: {orders.map((o) => `${o.customer} ${o.order} due ${o.due}${o.penalty ? " (penalty clause)" : ""}`).join("; ")}.
          </p>
          {c && <p>Estimated cost increase: <b>{inr(c.total_delta)}</b> ({c.formula}). Excludes {c.excluded.join(", ")}.</p>}
          {rejected.length > 0 && <p>The cheapest listed alternate, {rejected.map((a) => a.id).join(", ")}, was previously rejected. See the decision above.</p>}
          <p className="text-muted">Every sentence above is generated from the query results on this page, not by a language model.</p>
        </div>
      );
    }
    case "How it was computed":
      return (
        <div className="space-y-3">
          <p className="text-muted">
            {r.trace.length} Cypher queries against FalkorDB, {r.trace.reduce((s, t) => s + t.ms, 0).toFixed(0)} ms in total.
            Cost arithmetic and stock allocation are deterministic Python. {c && <>Assumptions: {[...c.assumptions, ...r.assumptions].join("; ")}.</>}
          </p>
          {r.trace.map((t, i) => (
            <details key={i} className="rounded-lg border border-line">
              <summary className="cursor-pointer px-3 py-2">
                <span className="font-mono">{t.name}</span>{" "}
                <span className="text-xs text-muted">{t.rows} rows · {t.ms} ms · {JSON.stringify(t.params)}</span>
              </summary>
              <pre className="overflow-x-auto border-t border-line bg-bg p-3 text-xs">{t.cypher}</pre>
            </details>
          ))}
        </div>
      );
  }
}
