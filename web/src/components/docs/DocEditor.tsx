"use client";

import {
  AlertTriangle, ArrowLeft, Check, CheckCheck, CircleAlert, Download, FileDown, Info, Loader2, PanelRightClose,
  PanelRightOpen, Plus, Save, Search, ShieldCheck, Sparkles, Wand2, X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { toast } from "sonner";
import { motion } from "motion/react";
import "superdoc/style.css";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import { api, ApiError, viewerId } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";
import { pendingKey } from "@/components/docs/DocsHome";

// The parts of SuperDoc's Document API that Neura1 uses. Calls may return values or promises; both are awaited.
type Block = { nodeId: string; type: string; text: string; headingLevel?: number };
type Target = { kind: "selection"; start: { kind: "text"; blockId: string; offset: number }; end: { kind: "text"; blockId: string; offset: number } };
type Sel = { empty: boolean; text?: string; target: { segments?: { blockId: string }[] } | null;
             selectionTarget: { start?: { blockId?: string; offset?: number }; end?: { blockId?: string; offset?: number } } | null };
type Receipt = { success?: boolean; failure?: { message?: string } };
type DocApi = {
  extract(i: object): Promise<{ blocks: Block[] }> | { blocks: Block[] };
  replace(i: object, o?: object): Promise<Receipt> | Receipt;
  insert(i: object, o?: object): Promise<Receipt> | Receipt;
  delete(i: object, o?: object): Promise<Receipt> | Receipt;
  getHtml(i: object): Promise<string> | string;
  selection: { current(i?: object): Promise<Sel> | Sel };
  comments: { create(i: object): Promise<Receipt> | Receipt };
  trackChanges: { list(i?: object): Promise<{ items: { id: string; author?: string }[] }> | { items: { id: string; author?: string }[] };
                  decide(i: object): Promise<Receipt> | Receipt };
};
type SD = {
  activeEditor: { doc: DocApi } | null;
  export(o: object): Promise<Blob>;
  setDocumentMode(m: string): void;
  search(t: string): unknown[] | undefined;
  goToSearchResult(m: unknown): boolean | undefined;
  destroy(): void;
};
type Meta = { id: string; title: string; kind: string; version: number; audience: string | null; about: string | null;
              has_file: boolean; updated_at: string; updated_by: string | null; created_by: string };
type Flag = { block_id: string; quote: string; severity: "error" | "warning" | "info"; title: string; message: string;
              record: string | null; sources: string[] };
type Run = { instruction: string; scope: string; pending: boolean; note?: string; applied?: number; warnings?: string[];
             error?: string; facts?: string[] };
type Hit = { id: string; label: string; name: string };

const AI_AUTHOR = "Neura1 AI";
const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const QUICK = ["Improve clarity", "Make it shorter", "Make it more formal", "Fix grammar and spelling",
               "Rewrite for a customer, without internal jargon", "Translate to Kannada", "Translate to Hindi"];
const INSERTS: { kind: string; label: string; for: string[] }[] = [
  { kind: "where_used", label: "Where used", for: ["Item"] },
  { kind: "decisions", label: "Decisions", for: ["Item"] },
  { kind: "orders", label: "Open orders", for: ["Customer"] },
  { kind: "owners", label: "Who knows", for: ["Item", "Customer", "Project", "Person"] },
  { kind: "history", label: "History", for: ["Item", "Customer", "Project", "Person", "Order", "Build"] },
];

/** The editor's selection now, or the last one seen if focus has moved to the panel. */
async function liveSelection(d: DocApi, last: Sel | null): Promise<Sel | null> {
  try {
    const s = await d.selection.current({ includeText: true });
    if (s && (s.selectionTarget || s.target)) return s;
  } catch {}
  return last;
}

const blockRange = (blockId: string, start: number, end: number): Target =>
  ({ kind: "selection", start: { kind: "text", blockId, offset: start }, end: { kind: "text", blockId, offset: end } });

/** The smallest changed span between two versions of a paragraph, widened to whole words. */
function changedSpan(before: string, after: string) {
  let p = 0;
  while (p < before.length && p < after.length && before[p] === after[p]) p++;
  let s = 0;
  while (s < before.length - p && s < after.length - p && before[before.length - 1 - s] === after[after.length - 1 - s]) s++;
  while (p > 0 && /\S/.test(before[p - 1])) p--;
  while (s > 0 && /\S/.test(before[before.length - s])) s--;
  return { start: p, end: before.length - s, text: after.slice(p, after.length - s) };
}

/** Apply one paragraph's new text as the smallest tracked change, relative to `base` within the paragraph. */
async function applyDiff(d: DocApi, blockId: string, base: number, before: string, after: string, full: string): Promise<boolean> {
  const opts = { changeMode: "tracked", author: { name: AI_AUTHOR } };
  let { start, end, text: piece } = changedSpan(before, after);
  if (start === end && !piece) return false;
  start += base; end += base;
  if (start === end) {
    // A pure insertion: anchor it on a neighbouring character so it shows as one tracked replacement.
    if (start < full.length) { piece = piece + full[start]; end = start + 1; }
    else if (start > 0) { piece = full[start - 1] + piece; start -= 1; }
  }
  const target = blockRange(blockId, start, end);
  const r = piece ? await d.replace({ target, text: piece }, opts) : await d.delete({ target }, opts);
  return r?.success !== false;
}

export default function DocEditor({ id }: { id: string }) {
  const host = useRef<HTMLDivElement>(null);
  const sdRef = useRef<SD | null>(null);
  const lastSel = useRef<Sel | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [title, setTitle] = useState("");
  const [ready, setReady] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState("editing");
  const [panel, setPanel] = useState(true);
  const [tab, setTab] = useState<"edit" | "check" | "insert">("edit");
  const [selText, setSelText] = useState("");

  const doc = useCallback(() => {
    const d = sdRef.current?.activeEditor?.doc;
    if (!d) throw new Error("The editor is still opening");
    return d;
  }, []);

  // ---------- open ----------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const m = await api<Meta>(`/api/docs/${id}`);
        if (cancelled) return;
        setMeta(m); setTitle(m.title);
        let source: File | undefined;
        if (m.has_file) {
          const res = await fetch(`/api/docs/${id}/file`, { headers: { "x-neura1-as": viewerId() } });
          if (!res.ok) throw new Error("Could not load the saved file");
          source = new File([await res.blob()], `${m.title}.docx`, { type: DOCX });
        }
        // SuperDoc is built on Vue, which reads these build flags as globals when they are not compiled in.
        Object.assign(globalThis, { __VUE_OPTIONS_API__: true, __VUE_PROD_DEVTOOLS__: false, __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: false });
        const { SuperDoc } = await import("superdoc");
        if (cancelled || !host.current) return;
        const me = await api<{ id: string | null; name: string }>("/api/viewer").catch(() => ({ id: viewerId(), name: "Flyvi" }));
        const sd = new SuperDoc({
          selector: host.current, toolbar: "#neura1-doc-toolbar", documentMode: "editing",
          user: { name: me.name, email: `${(me.id ?? "user").toLowerCase()}@flyvi.local` },
          ...(source ? { document: source } : {}),
          onReady: async () => {
            if (cancelled) return;
            sdRef.current = sd as unknown as SD;
            (window as unknown as { neura1Doc?: SD }).neura1Doc = sd as unknown as SD;  // for scripted demos and tests
            if (!m.has_file) {
              let md: string | null = null;
              try { md = sessionStorage.getItem(pendingKey(id)); } catch {}
              if (md && md.trim()) {
                await (sd as unknown as SD).activeEditor?.doc.replace({ value: md, type: "markdown", target: { kind: "story", storyType: "body" } });
                setDirty(true);
              }
            }
            setReady(true);
          },
          onTransaction: () => {
            const d = (sd as unknown as SD).activeEditor?.doc;
            if (!d) return;
            Promise.resolve(d.selection.current({ includeText: true })).then((s) => {
              if (s && (s.selectionTarget || s.target)) { lastSel.current = s; setSelText(s.empty ? "" : s.text ?? ""); }
            }).catch(() => {});
          },
          onEditorUpdate: () => setDirty(true),
          onException: (e: { error?: Error }) => setError(e?.error?.message ?? "The editor hit a problem"),
        } as never) as unknown as SD;
        if (cancelled) sd.destroy();
        else sdRef.current = sd;
      } catch (e) {
        setError(e instanceof ApiError && e.status === 403 ? "You can't open this document: " + e.message : (e as Error).message);
      }
    })();
    return () => { cancelled = true; sdRef.current?.destroy(); sdRef.current = null; };
  }, [id]);

  // Keep the panel's view of the selection current as the user selects with mouse or keyboard.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const read = () => {
      const d = sdRef.current?.activeEditor?.doc;
      if (!d) return;
      Promise.resolve(d.selection.current({ includeText: true })).then((s) => {
        if (s && (s.selectionTarget || s.target)) { lastSel.current = s; setSelText(s.empty ? "" : s.text ?? ""); }
      }).catch(() => {});
    };
    el.addEventListener("mouseup", read);
    el.addEventListener("keyup", read);
    return () => { el.removeEventListener("mouseup", read); el.removeEventListener("keyup", read); };
  }, []);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // ---------- save, export ----------
  const save = useCallback(async () => {
    const c = credentials();
    if (!c || !sdRef.current) return;
    setStatus("Saving…");
    try {
      const blob = await sdRef.current.export({ triggerDownload: false });
      const ex = await doc().extract({});
      const form = new FormData();
      form.append("file", new File([blob], `${title || "document"}.docx`, { type: DOCX }));
      form.append("title", title || "Untitled document");
      form.append("blocks", JSON.stringify(ex.blocks.map((b) => b.text)));
      const res = await fetch(`/api/docs/${id}`, { method: "PUT", body: form,
        headers: { "x-neura1-as": viewerId(), "x-demo-passcode": c.pass } });
      const body = await res.json().catch(() => ({}));
      if (res.status === 403) forgetPasscode();
      if (!res.ok) throw new Error(body.detail ?? "Save failed");
      try { sessionStorage.removeItem(pendingKey(id)); } catch {}
      setMeta((m) => (m ? { ...m, ...body, has_file: true } : m));
      setDirty(false);
      toast.success(`Saved version ${body.version}`, { description: body.shared
        ? `${body.passages} passages${body.linked?.length ? `, linked to ${body.linked.slice(0, 4).join(", ")}${body.linked.length > 4 ? "…" : ""}` : ""}`
        : "Kept private: it states someone's leave" });
      setStatus(body.shared
        ? `Saved · version ${body.version} · ${body.passages} passages${body.linked?.length ? ` linked to ${body.linked.slice(0, 5).join(", ")}${body.linked.length > 5 ? "…" : ""}` : ""}`
        : `Saved · version ${body.version} · kept private (it states someone's leave)`);
    } catch (e) {
      setStatus(""); setError((e as Error).message); toast.error("Could not save", { description: (e as Error).message });
    }
  }, [doc, id, title]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); save(); } };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [save]);

  async function downloadDocx() {
    await sdRef.current?.export({ exportedName: title || "document", triggerDownload: true });
  }

  async function exportPdf() {
    const html = await doc().getHtml({});
    const w = window.open("", "_blank");
    if (!w) { setError("Allow pop-ups to export a PDF"); return; }
    w.document.write(`<!doctype html><html><head><title>${(title || "document").replace(/</g, "")}</title><style>
      @page { size: A4; margin: 22mm 20mm; } body { font: 11pt/1.5 Calibri, Arial, sans-serif; color: #111; }
      h1 { font-size: 20pt; margin: 0 0 12pt; } h2 { font-size: 14pt; margin: 18pt 0 6pt; } h3 { font-size: 12pt; }
      table { border-collapse: collapse; width: 100%; margin: 6pt 0 12pt; } td, th { border: 1px solid #999; padding: 4pt 6pt; text-align: left; vertical-align: top; }
      th { background: #f0f2f5; } p { margin: 0 0 8pt; } ins { color: #0a6b2d; } del { color: #a11; }
    </style></head><body>${html}</body></html>`);
    w.document.close();
    w.focus();
    setTimeout(() => w.print(), 300);
  }

  function changeMode(m: string) {
    setMode(m);
    sdRef.current?.setDocumentMode(m);
  }

  async function decideAi(decision: "accept" | "reject") {
    const d = doc();
    const list = await d.trackChanges.list({});
    const ids = list.items.filter((x) => !x.author || x.author === AI_AUTHOR).map((x) => x.id);
    if (ids.length) await d.trackChanges.decide({ decision, target: { kind: "ids", ids } });
    setStatus(ids.length ? `${decision === "accept" ? "Accepted" : "Rejected"} ${ids.length} AI change${ids.length === 1 ? "" : "s"}` : "No AI changes to review");
  }

  function find(quote: string) {
    const sd = sdRef.current;
    const m = sd?.search(quote);
    if (m && m.length) sd?.goToSearchResult(m[0]);
  }

  return (
    <div className="-mb-12 flex h-[calc(100dvh-7rem)] flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Link href="/docs" className="rounded-lg p-2 text-muted hover:bg-elev hover:text-ink" title="All documents"><ArrowLeft size={16} /></Link>
        <input value={title} onChange={(e) => { setTitle(e.target.value); setDirty(true); }}
               className="min-w-0 flex-1 rounded-lg border border-transparent bg-transparent px-2 py-1.5 text-lg font-semibold tracking-tight hover:border-line focus:border-line"
               aria-label="Document title" />
        <span className="hidden text-xs text-muted lg:inline">{status || (dirty ? "Unsaved changes" : meta?.version ? `Version ${meta.version}` : "")}</span>
        <select value={mode} onChange={(e) => changeMode(e.target.value)} disabled={!ready}
                className="rounded-lg border border-line bg-elev px-2 py-1.5 text-xs" title="Editing changes the text; Suggesting records your edits as tracked changes">
          <option value="editing">Editing</option><option value="suggesting">Suggesting</option><option value="viewing">Viewing</option>
        </select>
        <button onClick={save} disabled={!ready} className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm text-white hover:bg-accent-hover disabled:opacity-50"><Save size={14} /> Save</button>
        <button onClick={downloadDocx} disabled={!ready} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm hover:border-line2 disabled:opacity-50" title="Download as Word"><Download size={14} /> .docx</button>
        <button onClick={exportPdf} disabled={!ready} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm hover:border-line2 disabled:opacity-50" title="Print or save as PDF"><FileDown size={14} /> PDF</button>
        <button onClick={() => setPanel(!panel)} className="flex items-center gap-1.5 rounded-lg border border-cyan/25 bg-cyan/[0.07] px-3 py-1.5 text-sm text-cyan hover:bg-cyan/20">
          {panel ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />} Neura1 AI
        </button>
      </div>
      {error && <div className="flex items-start justify-between gap-2 rounded-lg border border-warn/25 bg-warn/[0.07] p-2.5 text-sm text-warn">
        {error}<button onClick={() => setError(null)}><X size={14} /></button></div>}

      <Group orientation="horizontal" className="min-h-0 flex-1">
        <Panel id="paper" minSize="40" className="flex min-w-0">
        <div className="neura1-paper flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-line">
          <div id="neura1-doc-toolbar" className="shrink-0 overflow-x-auto border-b border-[#dfe3ea] bg-white" />
          <div className="relative min-h-0 flex-1 overflow-auto bg-[#e9ecf1]">
            {!ready && !error && <div className="absolute inset-0 grid place-items-center text-sm text-[#5b6472]"><Loader2 className="animate-spin" /></div>}
            <div ref={host} className="mx-auto py-6" />
          </div>
        </div>
        </Panel>
        {panel && (
          <>
          <Separator className="group mx-1 flex w-2 items-center justify-center outline-none" aria-label="Resize the AI panel">
            <span className="h-10 w-1 rounded-full bg-line2 transition group-hover:bg-accent group-data-[separator=active]:bg-accent" />
          </Separator>
          <Panel id="ai" defaultSize={400} minSize={320} maxSize={640} className="flex">
          <aside className="card flex w-full flex-col overflow-hidden">
            <div className="flex border-b border-line text-sm">
              {([["edit", "Edit with AI", Wand2], ["check", "Check facts", ShieldCheck], ["insert", "Insert facts", Plus]] as const).map(([k, label, Icon]) => (
                <button key={k} onClick={() => setTab(k)}
                        className={`relative flex flex-1 items-center justify-center gap-1.5 py-2.5 ${tab === k ? "font-medium text-ink" : "text-muted hover:text-ink"}`}>
                  <Icon size={13} /> {label}
                  {tab === k && <motion.span layoutId="doc-ai-tab" className="absolute inset-x-3 -bottom-px h-[2px] rounded-full bg-accent"
                                             transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {/* Each tab keeps its own state while switching, so results are not lost. */}
              <div hidden={tab !== "edit"}><EditTab ready={ready} doc={doc} lastSel={lastSel} selText={selText} title={title} onDecide={decideAi} /></div>
              <div hidden={tab !== "check"}><CheckTab ready={ready} doc={doc} onFind={find} /></div>
              <div hidden={tab !== "insert"}><InsertTab ready={ready} doc={doc} lastSel={lastSel} /></div>
            </div>
          </aside>
          </Panel>
          </>
        )}
      </Group>
    </div>
  );
}

// ---------- Edit with AI ----------

function EditTab({ ready, doc, lastSel, selText, title, onDecide }: {
  ready: boolean; doc: () => DocApi; lastSel: React.RefObject<Sel | null>; selText: string; title: string;
  onDecide: (d: "accept" | "reject") => void;
}) {
  const [scope, setScope] = useState<"selection" | "section" | "document">("section");
  const [text, setText] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const busy = runs.some((r) => r.pending);

  useEffect(() => { if (selText.trim()) setTimeout(() => setScope("selection"), 0); }, [selText]);

  async function run(instruction: string) {
    if (!instruction.trim() || busy) return;
    setText("");
    setRuns((r) => [{ instruction, scope, pending: true }, ...r]);
    const update = (patch: Partial<Run>) => setRuns((r) => r.map((x, i) => (i === 0 ? { ...x, ...patch, pending: false } : x)));
    try {
      const d = doc();
      const blocks = (await d.extract({})).blocks;
      const sel = await liveSelection(d, lastSel.current);
      let send: { id: string; text: string }[] = [];
      let within: { blockId: string; from: number } | null = null;
      if (scope === "selection") {
        if (!sel || sel.empty || !sel.text?.trim() || !sel.selectionTarget) throw new Error("Select some text in the document first.");
        const st = sel.selectionTarget;
        const b = blocks.find((x) => x.nodeId === st.start?.blockId);
        if (b && st.start?.blockId === st.end?.blockId && st.start?.offset !== undefined && st.end?.offset !== undefined) {
          // Widen a selection inside one paragraph to whole words, so a half-selected word is never cut.
          let a = Math.min(st.start.offset, st.end.offset), z = Math.max(st.start.offset, st.end.offset);
          while (a > 0 && /\S/.test(b.text[a - 1])) a--;
          while (z < b.text.length && /\S/.test(b.text[z])) z++;
          within = { blockId: b.nodeId, from: a };
          send = [{ id: "selection", text: b.text.slice(a, z) }];
        } else {
          send = [{ id: "selection", text: sel.text }];
        }
      } else if (scope === "section") {
        const anchor = sel?.selectionTarget?.start?.blockId ?? sel?.target?.segments?.[0]?.blockId;
        const at = blocks.findIndex((b) => b.nodeId === anchor);
        if (at < 0) throw new Error("Click inside the section you want to change first.");
        let start = at;
        while (start > 0 && blocks[start].type !== "heading") start--;
        const level = blocks[start].type === "heading" ? blocks[start].headingLevel ?? 1 : 0;
        let end = at + 1;
        while (end < blocks.length && !(blocks[end].type === "heading" && (blocks[end].headingLevel ?? 1) <= level)) end++;
        send = blocks.slice(start, end).filter((b) => b.text.trim()).map((b) => ({ id: b.nodeId, text: b.text }));
      } else {
        send = blocks.filter((b) => b.text.trim()).map((b) => ({ id: b.nodeId, text: b.text }));
      }
      if (!send.length) throw new Error("There is no text in that part of the document.");
      const res = await api<{ edits: { id: string; text: string; before: string }[]; note: string; warnings: string[]; facts: string[] }>(
        "/api/docs/ai", { method: "POST", body: JSON.stringify({ instruction, blocks: send, title }) });
      let applied = 0;
      for (const e of res.edits) {
        if (e.id === "selection" && within) {
          const now = (await d.extract({})).blocks.find((b) => b.nodeId === within.blockId);
          if (now && await applyDiff(d, within.blockId, within.from, send[0].text, e.text, now.text)) applied++;
        } else if (e.id === "selection") {
          const r = await d.replace({ target: sel!.selectionTarget, text: e.text }, { changeMode: "tracked", author: { name: AI_AUTHOR } });
          if (r?.success !== false) applied++;
        } else {
          const now = (await d.extract({})).blocks.find((b) => b.nodeId === e.id);
          if (now && await applyDiff(d, e.id, 0, now.text, e.text, now.text)) applied++;
        }
      }
      update({ note: res.note, applied, warnings: res.warnings, facts: res.facts });
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 503 ? "The AI model is not connected right now. Everything else in Docs works without it."
        : e instanceof ApiError && e.status === 413 ? String((e.body as { detail?: string })?.detail ?? e.message) : (e as Error).message;
      update({ error: msg });
    }
  }

  return (
    <div className="space-y-4 p-4">
      <div>
        <div className="text-[11px] uppercase tracking-[0.12em] text-muted">What to change</div>
        <div className="mt-1.5 grid grid-cols-3 gap-1 rounded-lg bg-elev p-1 text-xs">
          {(["selection", "section", "document"] as const).map((s) => (
            <button key={s} onClick={() => setScope(s)} className={`rounded-md py-1.5 capitalize ${scope === s ? "bg-panel text-ink shadow" : "text-muted hover:text-ink"}`}>
              {s === "document" ? "Whole document" : s}
            </button>
          ))}
        </div>
        <div className="mt-1.5 line-clamp-2 text-xs text-muted">
          {scope === "selection" ? (selText.trim() ? `“${selText.trim()}”` : "Select text in the document.")
            : scope === "section" ? "The section around your cursor, from its heading to the next one."
            : "Every paragraph. On a laptop CPU this takes a few minutes; on the DGX, seconds."}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {QUICK.map((q) => <button key={q} disabled={!ready || busy} onClick={() => run(q)}
                                  className="rounded-full border border-line px-2.5 py-1 text-xs text-muted hover:border-line2 hover:text-ink disabled:opacity-50">{q}</button>)}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); run(text); }} className="space-y-2">
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); run(text); } }}
                  placeholder="Tell Neura1 what to do, e.g. “Explain why NB54361-L is not an option, in two sentences” or “Make section 4 suitable for the customer”"
                  className="w-full resize-none rounded-xl border border-line px-3 py-2 text-sm" />
        <button disabled={!ready || busy || !text.trim()} className="flex w-full items-center justify-center gap-1.5 rounded-xl bg-accent py-2 text-sm text-white hover:bg-accent-hover disabled:opacity-50">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} {busy ? "Editing…" : "Edit"}
        </button>
      </form>
      <div className="flex gap-2">
        <button disabled={!ready} onClick={() => onDecide("accept")} className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-success/40 py-1.5 text-xs text-success hover:bg-success/10"><CheckCheck size={13} /> Accept AI changes</button>
        <button disabled={!ready} onClick={() => onDecide("reject")} className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-danger/40 py-1.5 text-xs text-danger hover:bg-danger/10"><X size={13} /> Reject AI changes</button>
      </div>
      <p className="text-xs text-muted">Edits arrive as tracked changes by “{AI_AUTHOR}”: review each in the document, or accept and reject them all here. Facts come from Flyvi&apos;s graph; any number or ID the model adds that isn&apos;t in the document or the records is flagged.</p>
      <div className="space-y-2">
        {runs.map((r, i) => (
          <div key={i} className="rounded-xl border border-line p-3 text-sm">
            <div className="text-xs text-muted">{r.scope === "document" ? "Whole document" : r.scope}</div>
            <div className="font-medium">{r.instruction}</div>
            {r.pending && <div className="mt-1 flex items-center gap-1.5 text-xs text-muted"><Loader2 size={12} className="animate-spin" /> Reading the graph and rewriting…</div>}
            {r.error && <div className="mt-1 text-xs text-warn">{r.error}</div>}
            {!r.pending && !r.error && (
              <div className="mt-1 space-y-1 text-xs">
                <div className="flex items-center gap-1.5 text-success"><Check size={12} /> {r.applied ? `${r.applied} change${r.applied === 1 ? "" : "s"} suggested` : "Nothing needed changing"}</div>
                {r.note && <div className="text-muted">{r.note}</div>}
                {r.warnings?.map((w) => <div key={w} className="flex gap-1.5 text-warn"><AlertTriangle size={12} className="mt-0.5 shrink-0" /> {w}</div>)}
                {!!r.facts?.length && <details className="text-muted"><summary className="cursor-pointer">{r.facts.length} facts from the graph</summary>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4">{r.facts.map((f) => <li key={f}>{f}</li>)}</ul></details>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------- Check facts ----------

function CheckTab({ ready, doc, onFind }: { ready: boolean; doc: () => DocApi; onFind: (q: string) => void }) {
  const [flags, setFlags] = useState<Flag[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [commented, setCommented] = useState(false);
  const blocksRef = useRef<Block[]>([]);

  const run = useCallback(async () => {
    setBusy(true); setCommented(false);
    try {
      const blocks = (await doc().extract({})).blocks;
      blocksRef.current = blocks;
      const r = await api<{ flags: Flag[] }>("/api/docs/check", { method: "POST",
        body: JSON.stringify({ blocks: blocks.map((b) => ({ id: b.nodeId, text: b.text })) }) });
      setFlags(r.flags);
    } finally { setBusy(false); }
  }, [doc]);

  useEffect(() => { if (ready) setTimeout(() => { run().catch(() => {}); }, 0); }, [ready, run]);

  async function addComments() {
    const d = doc();
    for (const f of flags ?? []) {
      const b = blocksRef.current.find((x) => x.nodeId === f.block_id);
      const at = b?.text.indexOf(f.quote) ?? -1;
      if (!b || at < 0) continue;
      await d.comments.create({ text: `Neura1: ${f.title}. ${f.message}`, target: { kind: "text", blockId: b.nodeId, range: { start: at, end: at + f.quote.length } } });
    }
    setCommented(true);
  }

  const tone = { error: "border-danger/25 bg-danger/[0.07] text-danger", warning: "border-warn/25 bg-warn/[0.07] text-warn", info: "border-line bg-elev text-muted" };
  const Icon = { error: CircleAlert, warning: AlertTriangle, info: Info };
  return (
    <div className="space-y-3 p-4">
      <p className="text-xs text-muted">Every claim is checked against Flyvi&apos;s records by fixed rules, not by a model: rejected or unapproved parts,
        expired quotes, obsolete revisions, prices that match no quote, people on leave, and IDs that don&apos;t exist.</p>
      <div className="flex gap-2">
        <button onClick={() => run()} disabled={!ready || busy} className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-accent py-1.5 text-sm text-white hover:bg-accent-hover disabled:opacity-50">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />} Check again</button>
        <button onClick={addComments} disabled={!flags?.length || commented} className="rounded-lg border border-line px-3 py-1.5 text-xs hover:border-line2 disabled:opacity-50">
          {commented ? "Added as comments" : "Add as Word comments"}</button>
      </div>
      {flags && flags.length === 0 && <div className="flex items-center gap-1.5 rounded-lg border border-success/25 bg-success/[0.07] p-3 text-sm text-success"><Check size={14} /> Nothing in this document contradicts the records.</div>}
      {flags?.map((f, i) => {
        const I = Icon[f.severity];
        return (
          <div key={i} className={`rounded-xl border p-3 text-sm ${tone[f.severity]}`}>
            <button onClick={() => onFind(f.quote)} className="flex w-full items-start gap-1.5 text-left font-medium" title="Show in the document">
              <I size={14} className="mt-0.5 shrink-0" /> {f.title}</button>
            <div className="mt-1 text-xs text-ink/80">{f.message}</div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
              <button onClick={() => onFind(f.quote)} className="flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-muted hover:text-ink"><Search size={10} /> “{f.quote}”</button>
              {f.record && <Link href={`/explore?id=${encodeURIComponent(f.record)}`} className="rounded-md border border-line px-1.5 py-0.5 text-muted hover:text-ink">{f.record} →</Link>}
              {f.sources.map((s) => <button key={s} onClick={() => setOpen(s)} className="rounded-md border border-line px-1.5 py-0.5 text-muted hover:text-ink">{s.split("/").pop()}</button>)}
            </div>
          </div>
        );
      })}
      {open && <EvidenceDrawer key={open} chunk={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

// ---------- Insert facts ----------

function InsertTab({ ready, doc, lastSel }: { ready: boolean; doc: () => DocApi; lastSel: React.RefObject<Sel | null> }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [rec, setRec] = useState<Hit | null>({ id: "NB54360", label: "Item", name: "NB54360" });
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(() => api<Hit[]>(`/api/lookup?q=${encodeURIComponent(q)}`).then(setHits).catch(() => {}), 150);
    return () => clearTimeout(t);
  }, [q]);

  async function insert(kind: string) {
    if (!rec) return;
    setMsg(null);
    try {
      const { markdown } = await api<{ markdown: string }>(`/api/docs-insert?kind=${kind}&record=${encodeURIComponent(rec.id)}`);
      const d = doc();
      const blocks = (await d.extract({})).blocks;
      const sel = await liveSelection(d, lastSel.current);
      const anchorId = sel?.selectionTarget?.start?.blockId ?? sel?.target?.segments?.[0]?.blockId;
      const anchor = blocks.find((b) => b.nodeId === anchorId);
      const r = anchor
        ? await d.insert({ value: markdown, type: "markdown", target: { kind: "block", nodeType: anchor.type, nodeId: anchor.nodeId }, placement: "after" })
        : await d.insert({ value: markdown, type: "markdown" });
      if (r?.success === false) throw new Error(r.failure?.message ?? "Could not insert here");
      setMsg(anchor ? "Inserted after your cursor." : "Inserted at the end of the document.");
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  return (
    <div className="space-y-3 p-4">
      <p className="text-xs text-muted">Insert live tables from the graph where your cursor is. Each one says when and where it came from.</p>
      <div className="relative">
        <div className="flex items-center gap-2 rounded-xl border border-line bg-elev px-3">
          <Search size={13} className="text-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="A part, customer, project or person…" className="h-9 flex-1 bg-transparent text-sm outline-none" style={{ background: "transparent" }} />
        </div>
        {q.length >= 2 && hits.length > 0 && (
          <div className="card absolute z-20 mt-1 w-full p-1">
            {hits.slice(0, 8).map((h) => (
              <button key={h.id} onClick={() => { setRec(h); setQ(""); setHits([]); }} className="block w-full truncate rounded-lg px-3 py-1.5 text-left text-sm hover:bg-elev">
                {h.name} <span className="text-xs text-muted">· {h.label}</span></button>
            ))}
          </div>
        )}
      </div>
      {rec && <div className="text-sm">Record: <span className="font-medium">{rec.name}</span> <span className="text-xs text-muted">({rec.label})</span></div>}
      <div className="grid grid-cols-2 gap-2">
        {INSERTS.filter((x) => rec && x.for.includes(rec.label)).map((x) => (
          <button key={x.kind} disabled={!ready} onClick={() => insert(x.kind)} className="rounded-lg border border-line px-3 py-2 text-left text-sm hover:border-line2 disabled:opacity-50">
            <Plus size={12} className="mr-1 inline" />{x.label}</button>
        ))}
      </div>
      {msg && <div className="text-xs text-muted">{msg}</div>}
    </div>
  );
}
