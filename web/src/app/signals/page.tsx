"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Notice = {
  id: string;
  title: string;
  version: string;
  extraction: null | {
    model: string;
    extracted_at: string;
    problems: string[];
    output: { part: string; change_types: string[]; new_unit_price: number | null; currency: string | null;
              effective_date: string | null; lead_weeks: number | null; last_time_buy?: string | null; supplier?: string | null };
  };
};

export default function Signals() {
  const [notices, setNotices] = useState<Notice[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = () => api<Notice[]>("/api/notices").then(setNotices).catch((e) => setError(e.message));
  useEffect(() => {
    api<Notice[]>("/api/notices").then(setNotices).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <section>
        <h1 className="page-title">Signals</h1>
        <p className="mt-1 text-sm text-muted">
          What arrives at Flyvi: supplier notices, customer escalations, leave notices. Each one opens the analysis that fits it.
        </p>
        <OtherSignals />
        {error && <p className="mt-4 text-sm text-danger">{error}</p>}
        <AddNotice onAdded={reload} />
        <div className="mt-4 space-y-3">
          {notices?.map((n) => (
            <div key={n.id} className="card p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted">Supplier notice</div>
                  <div className="mt-0.5 font-medium">{n.title}</div>
                  <div className="mt-1 font-mono text-xs text-muted">{n.id}</div>
                </div>
                {n.extraction && !n.extraction.problems.length ? (
                  <Link href={`/impact?source=${encodeURIComponent(n.id)}`}
                        className="shrink-0 rounded-lg bg-accent px-4 py-2 text-sm text-white hover:bg-accent-hover">
                    Trace impact
                  </Link>
                ) : null}
              </div>
              {n.extraction ? (
                <div className="mt-3 rounded-lg bg-bg p-3 text-sm">
                  <div className="flex flex-wrap gap-x-6 gap-y-1">
                    <span><b>{n.extraction.output.part}</b></span>
                    <span>{n.extraction.output.change_types.join(", ")}</span>
                    <span>new price {n.extraction.output.new_unit_price ?? "—"} {n.extraction.output.currency}</span>
                    <span>lead time {n.extraction.output.lead_weeks ?? "—"} wk</span>
                    <span>effective {n.extraction.output.effective_date ?? "—"}</span>
                  </div>
                  <div className="mt-2 text-xs text-muted">
                    {n.extraction.model.startsWith("entered by") ? `Facts ${n.extraction.model}` : `Read by ${n.extraction.model}`} at{" "}
                    {n.extraction.extracted_at.replace("T", " ").slice(0, 16)}. Every number was checked against the notice text.
                  </div>
                  {n.extraction.problems.map((p) => (
                    <div key={p} className="mt-1 text-xs text-danger">Verification failed: {p}</div>
                  ))}
                </div>
              ) : (
                <ManualFacts sourceId={n.id} onSaved={reload} />
              )}
            </div>
          ))}
        </div>
      </section>
      <div className="space-y-4">
        <WhatIf />
        <DemoUpdates />
      </div>
    </div>
  );
}

type Signal = { id: string; kind: string; title: string; date: string | null; subject: string | null; investigation: string | null };

const ROUTE: Record<string, (s: Signal) => string> = {
  escalation: (s) => `/customers?id=${s.subject}`,
  leave: (s) => `/people?id=${s.subject}&absence=1`,
};

function OtherSignals() {
  const [list, setList] = useState<Signal[]>([]);
  useEffect(() => { api<Signal[]>("/api/signals").then((x) => setList(x.filter((s) => s.kind !== "notice"))); }, []);
  if (!list.length) return null;
  return (
    <div className="mt-4 space-y-3">
      {list.map((s) => (
        <div key={s.id} className="card flex items-start justify-between gap-4 p-4">
          <div>
            <div className="text-xs uppercase tracking-wide text-muted">{s.kind === "escalation" ? "Customer escalation" : "Leave notice"} · {s.date?.slice(0, 10)}</div>
            <div className="mt-0.5 font-medium">{s.title}</div>
            <div className="mt-1 font-mono text-xs text-muted">{s.id}</div>
          </div>
          <Link href={ROUTE[s.kind](s)} className="shrink-0 rounded-lg bg-accent px-4 py-2 text-sm text-white hover:bg-accent-hover">
            {s.investigation ? "Open plan" : s.kind === "escalation" ? "Analyse account" : "Plan handover"}
          </Link>
        </div>
      ))}
    </div>
  );
}

function getPass(): string {
  let pass = "";
  try { pass = localStorage.getItem("neura1-passcode") ?? ""; } catch {}
  pass = pass || prompt("Demo passcode") || "";
  try { if (pass) localStorage.setItem("neura1-passcode", pass); } catch {}
  return pass;
}

function AddNotice({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    const pass = getPass();
    if (!pass) return;
    const f = new FormData();
    if (file) f.append("file", file);
    else f.append("text", text);
    setBusy(true);
    setMsg("Saving. If a model is connected it reads the notice, which can take a minute on a CPU…");
    const res = await fetch("/api/notices", { method: "POST", body: f, headers: { "x-demo-passcode": pass } });
    const body = await res.json();
    setBusy(false);
    if (!res.ok) {
      if (res.status === 403) try { localStorage.removeItem("neura1-passcode"); } catch {}
      return setMsg(`Could not add: ${body.detail ?? res.status}`);
    }
    setMsg(body.extraction ? "Added and read. Check the extracted facts below." :
      "Added. No model read it, so enter the facts below. They are checked against the notice text.");
    setText(""); setFile(null); setOpen(false);
    onAdded();
  }

  if (!open) return (
    <div className="mt-4">
      <button onClick={() => setOpen(true)} className="rounded-lg border border-ink px-4 py-2 text-sm font-medium hover:bg-accent hover:text-white hover:border-accent">
        + Add a supplier notice
      </button>
      {msg && <span className="ml-3 text-sm text-muted">{msg}</span>}
    </div>
  );
  return (
    <div className="card mt-4 space-y-3 p-4 text-sm">
      <div className="font-medium">Paste the supplier email, or upload the notice</div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} disabled={!!file}
                placeholder={"From: your distributor\nSubject: price change\n\nPart XYZ123 unit price changes to ₹410 from 2026-12-01, lead time 16 weeks…"}
                className="w-full rounded-md border border-line p-3 font-mono text-xs" />
      <div className="flex flex-wrap items-center gap-3">
        <input type="file" accept=".pdf,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-xs" />
        <button disabled={busy || (!text.trim() && !file)} onClick={submit}
                className="ml-auto rounded-lg bg-accent px-4 py-2 text-white disabled:opacity-40">{busy ? "Working…" : "Add notice"}</button>
        <button onClick={() => setOpen(false)} className="text-muted">Cancel</button>
      </div>
      {msg && <div className="text-muted">{msg}</div>}
    </div>
  );
}

function ManualFacts({ sourceId, onSaved }: { sourceId: string; onSaved: () => void }) {
  const [part, setPart] = useState("");
  const [price, setPrice] = useState("");
  const [lead, setLead] = useState("");
  const [eff, setEff] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  async function save() {
    const pass = getPass();
    if (!pass) return;
    let name = "";
    try { name = localStorage.getItem("neura1-reviewer") ?? ""; } catch {}
    name = name || prompt("Your name (recorded with the facts)") || "";
    if (!name) return;
    try { localStorage.setItem("neura1-reviewer", name); } catch {}
    const r = await api<{ problems: string[] }>("/api/notices/manual", {
      method: "POST", write: true,
      body: JSON.stringify({ source_id: sourceId, part, entered_by: name, currency: "INR",
                             new_unit_price: price ? Number(price) : null, lead_weeks: lead ? Number(lead) : null,
                             effective_date: eff || null }),
    }).catch((e) => ({ problems: [(e as Error).message] }));
    if (r.problems.length) setMsg(r.problems.join("; "));
    else onSaved();
  }

  return (
    <div className="mt-3 rounded-lg border border-dashed border-line p-3 text-sm">
      <div className="text-muted">Not read by a model. Enter what the notice says:</div>
      <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-4">
        <input value={part} onChange={(e) => setPart(e.target.value)} placeholder="Part number" className="rounded-md border border-line px-2 py-1.5 font-mono" />
        <input value={price} onChange={(e) => setPrice(e.target.value)} placeholder="New price (INR)" inputMode="decimal" className="rounded-md border border-line px-2 py-1.5" />
        <input value={lead} onChange={(e) => setLead(e.target.value)} placeholder="Lead time (weeks)" inputMode="numeric" className="rounded-md border border-line px-2 py-1.5" />
        <input value={eff} onChange={(e) => setEff(e.target.value)} placeholder="Effective (YYYY-MM-DD)" className="rounded-md border border-line px-2 py-1.5" />
      </div>
      <button disabled={!part} onClick={save} className="mt-2 rounded-md bg-accent px-3 py-1.5 text-white disabled:opacity-40">Save facts</button>
      {msg && <div className="mt-2 text-danger">Check failed: {msg}</div>}
    </div>
  );
}

function WhatIf() {
  const router = useRouter();
  const [item, setItem] = useState("");
  const [price, setPrice] = useState("");
  const [lead, setLead] = useState("");
  return (
    <aside className="card h-fit p-4">
      <h2 className="font-medium">What if a part changes?</h2>
      <p className="mt-1 text-sm text-muted">Trace any part with a price or lead time you choose.</p>
      <form
        className="mt-4 space-y-3 text-sm"
        onSubmit={(e) => {
          e.preventDefault();
          const q = new URLSearchParams({ item, ...(price && { price }), ...(lead && { lead }) });
          router.push(`/impact?${q}`);
        }}
      >
        <label className="block">
          <span className="text-muted">Part number</span>
          <input required value={item} onChange={(e) => setItem(e.target.value)} placeholder="e.g. NB54360"
                 className="mt-1 w-full rounded-md border border-line px-3 py-2 font-mono" />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-muted">New unit price (INR)</span>
            <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal"
                   className="mt-1 w-full rounded-md border border-line px-3 py-2" />
          </label>
          <label className="block">
            <span className="text-muted">Lead time (weeks)</span>
            <input value={lead} onChange={(e) => setLead(e.target.value)} inputMode="numeric"
                   className="mt-1 w-full rounded-md border border-line px-3 py-2" />
          </label>
        </div>
        <button className="w-full rounded-lg border border-ink px-4 py-2 font-medium hover:bg-accent hover:text-white hover:border-accent">
          Trace
        </button>
      </form>
    </aside>
  );
}

function DemoUpdates() {
  const [msg, setMsg] = useState<string | null>(null);
  async function apply() {
    let pass = "";
    try { pass = localStorage.getItem("neura1-passcode") ?? ""; } catch {}
    pass = pass || prompt("Demo passcode") || "";
    if (!pass) return;
    try {
      const r = await fetch("/api/updates/apply", { method: "POST", headers: { "x-demo-passcode": pass } });
      if (!r.ok) throw new Error(r.status === 403 ? "Wrong passcode" : `Failed (${r.status})`);
      try { localStorage.setItem("neura1-passcode", pass); } catch {}
      const body = await r.json();
      setMsg(`Loaded ${Object.keys(body.loaded).length} new sources. Re-open the impact view to see what changed.`);
    } catch (e) {
      setMsg((e as Error).message);
    }
  }
  return (
    <aside className="card p-4 text-sm">
      <div className="font-medium">Demo: new information arrives</div>
      <p className="mt-1 text-muted">
        17 Oct: Raghavendra posts a bench result for MX-3360 in #hw-power, and Sahyadri Electronics sends a quote.
      </p>
      <button onClick={apply} className="mt-3 w-full rounded-lg border border-line px-3 py-1.5 hover:border-ink">Bring in the updates</button>
      {msg && <div className="mt-2 text-xs text-muted">{msg}</div>}
    </aside>
  );
}
