"use client";

import { PageTitle } from "@/components/ui";
import { FilePlus2, FileText, FileUp, Lock, ScrollText, Send, UserRoundCog } from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, viewerId } from "@/lib/api";
import { credentials } from "@/lib/session";

const DocEditor = dynamic(() => import("@/components/docs/DocEditor"), {
  ssr: false, loading: () => <div className="p-6 text-muted">Opening the editor…</div>,
});

type Doc = { id: string; title: string; kind: string; created_by: string; updated_at: string; updated_by: string | null;
             version: number; audience: string | null; words: number | null; about: string | null };
type Opt = { id: string; name: string };

export const pendingKey = (id: string) => `neura1-doc-md-${id}`;

const TEMPLATES = [
  { key: "change_notice", title: "Engineering change notice", icon: ScrollText,
    blurb: "Follows HB-ENG-04. Affected products, builds, orders, cost, rejected alternates and required reviews, filled from the graph." },
  { key: "customer_response", title: "Customer response", icon: Send,
    blurb: "A letter to a customer with their open orders and Flyvi's action plan, owner by owner." },
  { key: "handover", title: "Leave handover note", icon: UserRoundCog,
    blurb: "Follows HB-HR-02. Open work and who takes it, what the person owns, and knowledge at risk." },
] as const;

export default function DocsHome() {
  const params = useSearchParams();
  const id = params.get("id");
  if (id) return <DocEditor key={id} id={id} />;
  return <Library />;
}

function Library() {
  const router = useRouter();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [parts, setParts] = useState<Opt[]>([]);
  const [customers, setCustomers] = useState<Opt[]>([]);
  const [people, setPeople] = useState<Opt[]>([]);
  const [pick, setPick] = useState<Record<string, string>>({ change_notice: "NB54360", customer_response: "C-KONKAN", handover: "P-RAGHAVENDRA" });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Doc[]>("/api/docs").then(setDocs).catch(() => {});
    api<{ kind: string; subject: string; subject_name?: string }[]>("/api/signals").then((s) => {
      const notices = s.filter((x) => x.kind === "notice").map((x) => ({ id: x.subject, name: x.subject }));
      setParts(notices.length ? notices : [{ id: "NB54360", name: "NB54360" }]);
    }).catch(() => setParts([{ id: "NB54360", name: "NB54360" }]));
    api<{ id: string; name: string }[]>("/api/customers").then((c) => setCustomers(c.map((x) => ({ id: x.id, name: x.name })))).catch(() => {});
    api<{ id: string; name: string }[]>("/api/people").then((p) => setPeople(p.map((x) => ({ id: x.id, name: x.name })))).catch(() => {});
  }, []);

  async function start(template: string, record?: string, extra?: Record<string, string>) {
    if (!credentials()) return;
    setBusy(template); setError(null);
    try {
      const r = await api<{ id: string; markdown: string }>("/api/docs", {
        method: "POST", write: true, body: JSON.stringify({ template, record, ...extra }),
      });
      try { sessionStorage.setItem(pendingKey(r.id), r.markdown); } catch {}
      router.push(`/docs?id=${r.id}`);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 403 ? "You can't create this one: " + e.message : (e as Error).message);
    } finally { setBusy(null); }
  }

  async function importFile(f: File) {
    const c = credentials();
    if (!c) return;
    setBusy("import"); setError(null);
    const headers = { "x-neura1-as": viewerId(), "x-demo-passcode": c.pass };
    try {
      if (f.name.toLowerCase().endsWith(".docx")) {
        const r = await api<{ id: string }>("/api/docs", { method: "POST", write: true,
          body: JSON.stringify({ template: "import", title: f.name.replace(/\.docx$/i, "") }) });
        const form = new FormData();
        form.append("file", f); form.append("title", f.name.replace(/\.docx$/i, "")); form.append("blocks", "[]");
        const up = await fetch(`/api/docs/${r.id}`, { method: "PUT", body: form, headers });
        if (!up.ok) throw new Error((await up.json().catch(() => ({}))).detail ?? "Upload failed");
        router.push(`/docs?id=${r.id}`);
        return;
      }
      const form = new FormData();
      form.append("file", f);
      const res = await fetch("/api/docs-import", { method: "POST", body: form, headers });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? "Could not read the file");
      await start("import", undefined, { title: body.title, markdown: body.markdown });
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(null); }
  }

  const options: Record<string, Opt[]> = { change_notice: parts, customer_response: customers, handover: people };

  return (
    <div className="space-y-6">
      <div>
        <PageTitle>Write with the <em>brain</em></PageTitle>
        <p className="mt-1 max-w-3xl text-sm text-muted">Word documents written with the company brain. Start from a template filled from the graph,
          edit with the full editor, ask Neura1 to rewrite any part as tracked changes, and check every claim against Flyvi&apos;s records.
          Saved documents become knowledge, linked to the parts, people and orders they name.</p>
      </div>

      <section data-tour="templates" className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <button onClick={() => start("blank", undefined, { title: "Untitled document" })} disabled={!!busy}
                className="card flex flex-col items-start gap-2 p-4 text-left hover:border-line2 disabled:opacity-60">
          <FilePlus2 size={18} className="text-cyan" />
          <div className="font-medium">Blank document</div>
          <div className="text-xs text-muted">An empty Word page with the full toolbar and the AI editor.</div>
          <span className="mt-auto pt-2 text-xs text-accent-hover">{busy === "blank" ? "Creating…" : "Create →"}</span>
        </button>
        {TEMPLATES.map((t) => (
          <div key={t.key} className="card flex flex-col items-start gap-2 p-4">
            <t.icon size={18} className="text-cyan" />
            <div className="font-medium">{t.title}</div>
            <div className="text-xs text-muted">{t.blurb}</div>
            <select value={pick[t.key]} onChange={(e) => setPick({ ...pick, [t.key]: e.target.value })}
                    className="mt-auto w-full rounded-lg border border-line bg-elev px-2 py-1.5 text-xs">
              {(options[t.key].length ? options[t.key] : [{ id: pick[t.key], name: pick[t.key] }]).map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
            <button onClick={() => start(t.key, pick[t.key])} disabled={!!busy}
                    className="text-xs text-accent-hover hover:underline disabled:opacity-60">{busy === t.key ? "Writing from the graph…" : "Create from the graph →"}</button>
          </div>
        ))}
        <button onClick={() => file.current?.click()} disabled={!!busy}
                className="card flex flex-col items-start gap-2 p-4 text-left hover:border-line2 disabled:opacity-60">
          <FileUp size={18} className="text-cyan" />
          <div className="font-medium">Open a file</div>
          <div className="text-xs text-muted">Word (.docx) opens as it is, with its layout, tables and tracked changes. PDF, Markdown and text become an editable document.</div>
          <span className="mt-auto pt-2 text-xs text-accent-hover">{busy === "import" ? "Opening…" : "Choose a file →"}</span>
          <input ref={file} type="file" accept=".docx,.pdf,.md,.txt" hidden
                 onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) importFile(f); }} />
        </button>
      </section>
      {error && <div className="rounded-lg border border-warn/25 bg-warn/[0.07] p-3 text-sm text-warn">{error}</div>}

      <section className="card overflow-hidden">
        <div className="border-b border-line px-4 py-3 text-[11px] uppercase tracking-[0.12em] text-muted">Your company&apos;s documents</div>
        {docs.length === 0 && <div className="p-4 text-sm text-muted">No documents yet. Start one above.</div>}
        <ul className="divide-y divide-line">
          {docs.map((d) => (
            <li key={d.id}>
              <button onClick={() => router.push(`/docs?id=${d.id}`)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-elev">
                <FileText size={16} className="shrink-0 text-muted" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{d.title}</div>
                  <div className="truncate text-xs text-muted">
                    {d.kind.replace("_", " ")}{d.about ? ` · about ${d.about}` : ""} · {d.version ? `version ${d.version}` : "not saved yet"}
                    {d.words ? ` · ${d.words} words` : ""} · {d.updated_by ?? d.created_by} · {d.updated_at.slice(0, 10)}
                  </div>
                </div>
                {d.audience && d.audience !== "everyone" && (
                  <span className="flex items-center gap-1 rounded-md border border-line px-2 py-0.5 text-[11px] text-muted" title="Only people allowed to see this content can open it">
                    <Lock size={11} /> {d.audience.includes("leave") ? "leave details" : "amounts"}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
