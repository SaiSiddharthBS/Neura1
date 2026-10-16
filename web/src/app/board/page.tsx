"use client";

import { Avatar } from "@/components/ViewerSwitch";
import Link from "next/link";
import { ArrowRight, CircleDashed, CircleCheck, CircleDot, FileText, Inbox, OctagonAlert, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Task = {
  id: string; title: string; kind: string; why: string; status: string | null; created_at: string;
  updated_at: string | null; target: string | null; owner_id: string | null; owner: string | null;
  investigation: string | null; part: string | null; projects: string[]; sources: number;
};
type Board = {
  columns: Record<"open" | "in_progress" | "blocked" | "done", Task[]>;
  pipeline: { notices: number; awaiting_analysis: { id: string; title: string }[]; investigations: number;
              open: number; in_progress: number; blocked: number; done: number };
};

const COLUMNS = [
  { key: "open", title: "To do", icon: CircleDashed, tone: "text-muted" },
  { key: "in_progress", title: "In progress", icon: CircleDot, tone: "text-accent-hover" },
  { key: "blocked", title: "Blocked", icon: OctagonAlert, tone: "text-danger" },
  { key: "done", title: "Done", icon: CircleCheck, tone: "text-success" },
] as const;

const KIND: Record<string, string> = {
  engineering_review: "Engineering", firmware_review: "Firmware", requalification: "Quality",
  procurement: "Procurement", production_replan: "Production", customer_comms: "Sales", task: "Ask", work: "Work",
  handover: "Handover", interim_owner: "Handover", interim_lead: "Handover", handover_note: "Handover", confirm_handover: "Handover",
  customer_response: "Customer", root_cause: "Support", prioritise_fix: "Software", production_hold: "Production", executive_brief: "Leadership",
};

export default function Workboard() {
  const [b, setB] = useState<Board | null>(null);
  const [who, setWho] = useState("all");
  const [project, setProject] = useState("all");
  const [drag, setDrag] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => api<Board>("/api/board").then(setB), []);
  useEffect(() => { api<Board>("/api/board").then(setB); }, []);

  async function move(task: Task, status: string) {
    let pass = "", name = "";
    try { pass = localStorage.getItem("neura1-passcode") ?? ""; name = localStorage.getItem("neura1-reviewer") ?? ""; } catch {}
    pass = pass || prompt("Demo passcode") || "";
    name = name || prompt("Your name") || "";
    if (!pass || !name) return;
    try { localStorage.setItem("neura1-passcode", pass); localStorage.setItem("neura1-reviewer", name); } catch {}
    try {
      await api(`/api/actions/${task.id}/status`, { method: "POST", write: true, body: JSON.stringify({ status, by: name }) });
      setMsg(`Moved “${task.title}” to ${COLUMNS.find((c) => c.key === status)?.title}.`);
      load();
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) try { localStorage.removeItem("neura1-passcode"); } catch {}
      setMsg((e as Error).message);
    }
  }

  const all = b ? Object.values(b.columns).flat() : [];
  const owners = [...new Map(all.filter((t) => t.owner).map((t) => [t.owner_id, t.owner])).entries()];
  const projects = [...new Set(all.flatMap((t) => t.projects))];
  const visible = (t: Task) => (who === "all" || t.owner_id === who) && (project === "all" || t.projects.includes(project));
  const p = b?.pipeline;
  const total = p ? p.open + p.in_progress + p.blocked + p.done : 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Workboard</h1>
          <p className="mt-1 text-sm text-muted">Every task from approved investigations and the Ask agent, in one place. Drag cards to move them; every move is recorded in the graph.</p>
        </div>
        <div className="flex gap-2 text-sm">
          <select value={who} onChange={(e) => setWho(e.target.value)} className="rounded-lg border border-line px-3 py-1.5">
            <option value="all">Everyone</option>
            {owners.map(([id, name]) => <option key={id} value={id!}>{name}</option>)}
          </select>
          <select value={project} onChange={(e) => setProject(e.target.value)} className="rounded-lg border border-line px-3 py-1.5">
            <option value="all">All projects</option>
            {projects.map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        </div>
      </div>

      {p && (
        <section className="card p-4">
          <div className="mb-3 text-[11px] font-medium uppercase tracking-[0.12em] text-muted">Process</div>
          <div className="grid gap-2 md:grid-cols-5">
            {[
              { label: "Notices received", n: p.notices, icon: Inbox },
              { label: "Awaiting analysis", n: p.awaiting_analysis.length, icon: Zap, warn: p.awaiting_analysis.length > 0 },
              { label: "Investigations approved", n: p.investigations, icon: FileText },
              { label: "Tasks open or blocked", n: p.open + p.in_progress + p.blocked, icon: CircleDot, warn: p.blocked > 0 },
              { label: "Tasks done", n: p.done, icon: CircleCheck, of: total },
            ].map((s, i) => (
              <div key={s.label} className="relative flex items-center gap-3 rounded-xl bg-elev px-3 py-3">
                <s.icon size={18} className={s.warn ? "text-warn" : "text-accent-hover"} />
                <div>
                  <div className="text-xl font-semibold tabular-nums">{s.n}{s.of !== undefined ? <span className="text-sm text-muted"> / {s.of}</span> : null}</div>
                  <div className="text-xs text-muted">{s.label}</div>
                </div>
                {i < 4 && <ArrowRight size={14} className="absolute -right-2 top-1/2 hidden -translate-y-1/2 text-muted md:block" />}
              </div>
            ))}
          </div>
          {total > 0 && (
            <div className="mt-3 flex h-1.5 overflow-hidden rounded-full bg-elev">
              <div className="bg-success" style={{ width: `${(p.done / total) * 100}%` }} />
              <div className="bg-accent" style={{ width: `${(p.in_progress / total) * 100}%` }} />
              <div className="bg-danger" style={{ width: `${(p.blocked / total) * 100}%` }} />
            </div>
          )}
          {p.awaiting_analysis.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2 text-sm">
              {p.awaiting_analysis.map((n) => (
                <Link key={n.id} href={`/impact?source=${encodeURIComponent(n.id)}`} className="rounded-lg border border-warn/25 bg-warn/[0.07] px-3 py-1 text-warn hover:border-warn">
                  Analyse: {n.title} →
                </Link>
              ))}
            </div>
          )}
        </section>
      )}

      {msg && <div className="text-sm text-muted">{msg}</div>}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {COLUMNS.map((c) => {
          const tasks = (b?.columns[c.key] ?? []).filter(visible);
          return (
            <div key={c.key} onDragOver={(e) => e.preventDefault()}
                 onDrop={() => { const t = all.find((x) => x.id === drag); if (t && (t.status ?? "open") !== c.key) move(t, c.key); setDrag(null); }}
                 className={`card flex min-h-[320px] flex-col p-3 ${drag ? "border-line2" : ""}`}>
              <div className="mb-3 flex items-center gap-2 px-1 text-sm font-medium">
                <c.icon size={15} className={c.tone} /> {c.title}
                <span className="ml-auto rounded-full bg-elev px-2 text-xs text-muted tabular-nums">{tasks.length}</span>
              </div>
              <div className="flex flex-1 flex-col gap-2">
                {tasks.map((t) => (
                  <article key={t.id} draggable onDragStart={() => setDrag(t.id)} onDragEnd={() => setDrag(null)}
                           className={`cursor-grab rounded-xl border border-line bg-elev p-3 text-sm transition hover:border-line2 active:cursor-grabbing ${drag === t.id ? "opacity-40" : ""}`}>
                    <div className="mb-1.5 flex items-center gap-1.5">
                      <span className="rounded-md bg-accent/15 px-1.5 py-0.5 text-[10.5px] text-accent-hover">{KIND[t.kind] ?? t.kind}</span>
                      {t.projects.map((x) => <span key={x} className="rounded-md bg-violet/15 px-1.5 py-0.5 text-[10.5px] text-violet">{x}</span>)}
                    </div>
                    <div className="font-medium leading-snug">{t.title}</div>
                    <div className="mt-2 flex items-center gap-2 text-xs text-muted">
                      <Avatar name={t.owner ?? "?"} size={22} />
                      <span className="truncate">{t.owner ?? "Unassigned"}</span>
                      {t.sources > 0 && <span className="ml-auto flex items-center gap-1"><FileText size={11} />{t.sources}</span>}
                    </div>
                    {t.part && (
                      <Link href={`/impact?item=${t.part}`} className="mt-2 block truncate font-mono text-[11px] text-muted hover:text-ink">
                        from {t.investigation} · {t.part}
                      </Link>
                    )}
                    <div className="mt-2 flex gap-1">
                      {COLUMNS.filter((x) => x.key !== (t.status ?? "open")).map((x) => (
                        <button key={x.key} onClick={() => move(t, x.key)} title={`Move to ${x.title}`}
                                className="rounded-md border border-line px-1.5 py-0.5 text-[10.5px] text-muted hover:border-line2 hover:text-ink">{x.title}</button>
                      ))}
                    </div>
                  </article>
                ))}
                {!tasks.length && <div className="grid flex-1 place-items-center rounded-xl border border-dashed border-line text-xs text-muted">Drop tasks here</div>}
              </div>
            </div>
          );
        })}
      </section>
    </div>
  );
}
