"use client";

import { toast } from "sonner";
import { ClipboardCheck } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";

export type Draft = { owner: string; title: string; target: string | null; why: string };

export default function DraftTask({ d }: { d: Draft }) {
  const [state, setState] = useState<string | null>(null);
  async function create() {
    let pass = "", name = "";
    try { pass = localStorage.getItem("neura1-passcode") ?? ""; name = localStorage.getItem("neura1-reviewer") ?? ""; } catch {}
    pass = pass || prompt("Demo passcode") || "";
    name = name || prompt("Your name") || "";
    if (!pass || !name) return;
    try { localStorage.setItem("neura1-passcode", pass); localStorage.setItem("neura1-reviewer", name); } catch {}
    try {
      const r = await api<{ id: string; new: boolean; owner: string | null }>("/api/tasks", { method: "POST", write: true, body: JSON.stringify({ ...d, created_by: name }) });
      setState(r.new ? `Created ${r.id} for ${r.owner ?? "nobody (owner not found)"}` : `Already exists (${r.id})`);
      if (r.new) toast.success(`Task created for ${r.owner ?? "nobody"}`, { description: d.title });
    } catch (e) { setState((e as Error).message); }
  }
  return (
    <div className="rounded-xl border border-accent/25 bg-accent/[0.07] p-3 text-sm">
      <div className="flex items-center gap-2 font-medium text-accent-hover"><ClipboardCheck size={15} /> Draft task, not created yet</div>
      <div className="mt-1"><b>{d.title}</b> → {d.owner}{d.target ? ` · ${d.target}` : ""}</div>
      {d.why && <div className="text-xs text-muted">{d.why}</div>}
      {state ? <div className="mt-2 text-xs">{state}</div> : <button onClick={create} className="mt-2 rounded-md bg-accent px-3 py-1 text-xs text-white">Create task</button>}
    </div>
  );
}
