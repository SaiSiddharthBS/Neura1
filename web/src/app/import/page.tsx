"use client";

import { Download, FileUp } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Template = { name: string; title: string; columns: string[]; required: string[]; help: string };
type Issue = { level: "error" | "warning"; file: string; row: number | null; column: string | null; message: string };
type Report = {
  ok: boolean; errors: number; warnings: number; issues: Issue[];
  files: { file: string; type: string; title: string; rows: number }[];
  documents: string[]; skipped: string[]; converted?: string[];
};

function passcode() {
  try { return localStorage.getItem("neura1-passcode") ?? ""; } catch { return ""; }
}

export default function ImportPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [rev, setRev] = useState("");

  useEffect(() => { api<Template[]>("/api/import/templates").then(setTemplates); }, []);

  function form(list = files, revision = rev) {
    const f = new FormData();
    list.forEach((x) => f.append("files", x));
    if (revision.trim()) f.append("eda_parent_rev", revision.trim());
    return f;
  }

  async function check(next: File[], revision = rev) {
    setFiles(next);
    setResult(null);
    if (!next.length) return setReport(null);
    const f = form(next, revision);
    setBusy(true);
    const res = await fetch("/api/import/validate", { method: "POST", body: f });
    setReport(await res.json());
    setBusy(false);
  }

  async function commit() {
    let pass = passcode();
    pass = pass || prompt("Demo passcode") || "";
    if (!pass) return;
    setBusy(true);
    const res = await fetch("/api/import/commit", { method: "POST", body: form(), headers: { "x-demo-passcode": pass } });
    const body = await res.json();
    setBusy(false);
    if (!res.ok) return setResult(`Import failed: ${body.detail ?? res.status}`);
    try { localStorage.setItem("neura1-passcode", pass); } catch {}
    const recs = Object.entries(body.records as Record<string, number>).map(([k, v]) => `${v} ${k}`).join(", ");
    const docs = Object.keys(body.documents ?? {}).length;
    setResult(`Imported ${recs || "no records"}${docs ? ` and ${docs} documents` : ""}. They are now part of the company graph.`);
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
      <section className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Bring in your company</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Drop the spreadsheets you already keep (BOM exports, item master, quotes, stock, builds, orders) and the documents
            where decisions live (Slack exports, tickets, test reports, PDFs). Everything is checked before anything is written.
          </p>
        </div>

        <label
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); check([...files, ...Array.from(e.dataTransfer.files)]); }}
          className={`card flex cursor-pointer flex-col items-center justify-center gap-2 border-2 border-dashed p-10 text-center ${drag ? "border-accent bg-accent/12" : ""}`}>
          <FileUp className="text-muted" />
          <div className="font-medium">Drop files here or click to choose</div>
          <div className="text-xs text-muted">.csv for records · .pdf .md .txt for documents · .json for Slack exports and tickets</div>
          <input type="file" multiple className="hidden"
                 onChange={(e) => check([...files, ...Array.from(e.target.files ?? [])])} />
        </label>

        {files.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {files.map((f) => <span key={f.name} className="rounded-md bg-panel px-2 py-1 font-mono text-xs ring-1 ring-line">{f.name}</span>)}
            <button onClick={() => check([])} className="text-xs text-muted underline">clear</button>
          </div>
        )}

        <label className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">BOM exported from KiCad, Altium or another CAD tool? It belongs to revision</span>
          <input value={rev} onChange={(e) => setRev(e.target.value)} onBlur={() => files.length && check(files, rev)}
                 placeholder="e.g. VC-200-C" className="w-40 rounded-md border border-line px-2 py-1 font-mono" />
        </label>

        {busy && <div className="text-sm text-muted">Checking…</div>}

        {report && !busy && (
          <div className="card">
            <div className={`flex items-center justify-between border-b border-line p-4 ${report.ok ? "" : "bg-danger/10"}`}>
              <div>
                <div className="font-medium">{report.ok ? "Ready to import" : "Fix these before importing"}</div>
                <div className="text-xs text-muted">
                  {report.files.filter((f) => f.rows > 0).map((f) => `${f.file} → ${f.title} (${f.rows} rows)`).join(" · ")}
                  {report.documents.length ? ` · ${report.documents.length} documents` : ""}
                  {report.converted?.map((c) => <div key={c}>Converted CAD BOM: {c}</div>)}
                </div>
              </div>
              <div className="text-sm"><b className="text-danger">{report.errors}</b> errors · <b className="text-warn">{report.warnings}</b> warnings</div>
            </div>
            {report.issues.length > 0 && (
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted"><tr>
                  {["", "File", "Row", "Column", "Problem"].map((h) => <th key={h} className="px-4 py-2 font-normal">{h}</th>)}
                </tr></thead>
                <tbody>
                  {report.issues.map((i, k) => (
                    <tr key={k} className="border-t border-line">
                      <td className="px-4 py-2"><span className={`rounded px-1.5 py-0.5 text-[10px] ${i.level === "error" ? "bg-danger/15 text-danger" : "bg-warn/15 text-warn"}`}>{i.level}</span></td>
                      <td className="px-4 py-2 font-mono text-xs">{i.file}</td>
                      <td className="px-4 py-2">{i.row ?? ""}</td>
                      <td className="px-4 py-2 font-mono text-xs">{i.column ?? ""}</td>
                      <td className="px-4 py-2">{i.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {report.skipped.map((s) => <div key={s} className="border-t border-line px-4 py-2 text-sm text-warn">Skipped {s}</div>)}
            <div className="border-t border-line p-4">
              <button disabled={!report.ok} onClick={commit}
                      className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-40">
                Import into the company graph
              </button>
              {result && <div className="mt-2 text-sm">{result}</div>}
            </div>
          </div>
        )}
      </section>

      <aside className="card h-fit p-4">
        <h2 className="font-medium">Templates</h2>
        <p className="mt-1 text-xs text-muted">
          Column names Neura1 understands. Export from your ERP, PLM or spreadsheet and rename columns to match, or download a
          template with an example row.
        </p>
        <ul className="mt-3 divide-y divide-line text-sm">
          {templates.map((t) => (
            <li key={t.name} className="py-2">
              <div className="flex items-center justify-between gap-2">
                <span>{t.title}</span>
                <a href={`/api/import/templates/${t.name}.csv`} className="flex items-center gap-1 text-xs text-accent hover:underline">
                  <Download size={12} /> {t.name}.csv
                </a>
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-muted">
                {t.columns.map((c) => (t.required.includes(c) ? c : `${c}?`)).join(", ")}
              </div>
              {t.help && <div className="mt-0.5 text-xs text-muted">{t.help}</div>}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
