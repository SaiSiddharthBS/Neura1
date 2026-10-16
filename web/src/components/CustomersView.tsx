"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, MessageSquareWarning, Ticket } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import PlanPanel, { type PlanAction, type PlanInvestigation } from "@/components/PlanPanel";
import { api, inr } from "@/lib/api";

type Row = { id: string; name: string; account_manager: string; orders: number; value: number };
type Detail = {
  customer: { id: string; name: string; account_manager: string; backup: string | null };
  orders: { id: string; qty: number; due: string; value: number; max_penalty: number; penalty_note: string; build: string;
            build_date: string; revision: string; planner: string; open_tasks: string[] }[];
  field_units: { id: string; qty: number; shipped_on: string; revision: string; status: string }[];
  signals: { source: string; kind: string; title: string; status: string | null; assignee: string | null; last: string }[];
  projects: { id: string; name: string; status: string; lead: string }[];
  who_knows: { id: string; name: string; role: string; score: number }[];
  open_value: number; share_of_book: number; rank: number; escalation: string | null;
  actions: PlanAction[]; investigation: PlanInvestigation;
};

export default function CustomersView() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const [rows, setRows] = useState<Row[]>([]);
  const [d, setD] = useState<Detail | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const load = useCallback(() => { if (id) api<Detail>(`/api/customers/${id}`).then(setD); }, [id]);

  useEffect(() => { api<Row[]>("/api/customers").then(setRows); }, []);
  useEffect(() => { if (id) api<Detail>(`/api/customers/${id}`).then(setD); }, [id]);
  const total = rows.reduce((s, r) => s + (r.value || 0), 0) || 1;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Customers</h1>
        <p className="mt-1 text-sm text-muted">Each account across sales, production, support and engineering: orders, field units, tickets, escalations and who knows them.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {rows.map((r) => (
          <button key={r.id} onClick={() => router.replace(`/customers?id=${r.id}`)}
                  className={`card p-4 text-left hover:border-line2 ${r.id === id ? "glow" : ""}`}>
            <div className="font-medium">{r.name}</div>
            <div className="mt-1 text-xs text-muted">{r.account_manager} · {r.orders} open orders</div>
            <div className="mt-3 flex items-end justify-between">
              <span className="text-xl font-semibold tabular-nums">{inr(r.value)}</span>
              <span className="text-xs text-muted">{Math.round((100 * r.value) / total)}% of order book</span>
            </div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-elev"><div className="h-full bg-gradient-to-r from-accent to-cyan" style={{ width: `${(100 * r.value) / total}%` }} /></div>
          </button>
        ))}
      </div>

      {d && (
        <div className="grid gap-4 lg:grid-cols-[1fr_420px]">
          <div className="space-y-4">
            {d.escalation && (
              <div className="flex items-start gap-3 rounded-2xl border border-danger/40 bg-danger/10 p-4 text-sm">
                <MessageSquareWarning className="mt-0.5 shrink-0 text-danger" size={18} />
                <div>
                  <div className="font-medium text-danger">Open escalation from {d.customer.name}</div>
                  <div className="mt-0.5">#{d.rank} account, {Math.round(d.share_of_book * 100)}% of open orders ({inr(d.open_value)}).</div>
                  <button onClick={() => setOpen(`${d.escalation}#p2`)} className="mt-2 rounded-md border border-danger/30 px-2 py-0.5 text-xs hover:border-danger">Read the escalation</button>
                </div>
              </div>
            )}
            <div className="card p-4">
              <div className="mb-2 text-[11px] uppercase tracking-[0.12em] text-muted">Orders</div>
              <table className="w-full text-sm">
                <thead className="text-xs text-muted"><tr>{["Order", "Due", "Value", "Penalty exposure", "Build", "Open tasks"].map((h) => <th key={h} className="py-1.5 text-left font-normal">{h}</th>)}</tr></thead>
                <tbody>{d.orders.map((o) => (
                  <tr key={o.id} className="border-t border-line align-top">
                    <td className="py-2 font-mono">{o.id}<div className="text-xs text-muted">{o.qty} × {o.revision}</div></td>
                    <td className="py-2">{o.due}</td>
                    <td className="py-2 tabular-nums">{inr(o.value)}</td>
                    <td className="py-2">{o.max_penalty ? <span className="text-warn">up to {inr(o.max_penalty)}</span> : "—"}</td>
                    <td className="py-2">{o.build}<div className="text-xs text-muted">{o.build_date} · {o.planner}</div></td>
                    <td className="py-2 text-xs">{o.open_tasks.length ? o.open_tasks.map((t) => <div key={t}>{t}</div>) : <span className="text-muted">none</span>}</td>
                  </tr>))}</tbody>
              </table>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="card p-4">
                <div className="mb-2 text-[11px] uppercase tracking-[0.12em] text-muted">Tickets and messages</div>
                {d.signals.map((s) => (
                  <button key={s.source} onClick={() => setOpen(`${s.source}#${s.kind === "ticket" ? "description" : "p2"}`)}
                          className="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-elev">
                    {s.kind === "ticket" ? <Ticket size={14} className="mt-0.5 text-muted" /> : s.kind === "escalation" ? <AlertTriangle size={14} className="mt-0.5 text-danger" /> : <span className="w-[14px]" />}
                    <span className="flex-1">{s.title}<span className="block text-xs text-muted">{s.kind}{s.status ? ` · ${s.status}` : ""}{s.assignee ? ` · ${s.assignee}` : ""}</span></span>
                  </button>
                ))}
              </div>
              <div className="card space-y-3 p-4 text-sm">
                <div>
                  <div className="mb-1 text-[11px] uppercase tracking-[0.12em] text-muted">Field units</div>
                  {d.field_units.length ? d.field_units.map((f) => <div key={f.id}>{f.qty} × {f.revision} <span className="text-xs text-muted">({f.status}, shipped {f.shipped_on})</span></div>) : <span className="text-muted">None</span>}
                </div>
                <div>
                  <div className="mb-1 text-[11px] uppercase tracking-[0.12em] text-muted">Projects</div>
                  {d.projects.length ? d.projects.map((p) => <Link key={p.id} href={`/projects?id=${p.id}`} className="block hover:underline">{p.name} <span className="text-xs text-muted">· {p.lead}</span></Link>) : <span className="text-muted">None</span>}
                </div>
                <div>
                  <div className="mb-1 text-[11px] uppercase tracking-[0.12em] text-muted">Who knows this account</div>
                  {d.who_knows.map((p) => <Link key={p.id} href={`/people?id=${p.id}`} className="mr-1.5 inline-block rounded-full bg-elev px-2 py-0.5 text-xs hover:bg-accent/20">{p.name}</Link>)}
                </div>
              </div>
            </div>
          </div>
          <PlanPanel title={d.escalation ? "Escalation plan" : "No open escalation"} kind="escalation" subject={d.customer.id}
                     actions={d.actions} investigation={d.investigation} onDone={load} />
        </div>
      )}
      {open && <EvidenceDrawer key={open} chunk={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
