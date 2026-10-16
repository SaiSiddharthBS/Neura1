"use client";

import { toast } from "sonner";
import Link from "next/link";
import { ClipboardCheck } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";

export type PlanAction = { kind: string; target: string; owner: string | null; title: string; why: string };
export type PlanInvestigation = { id: string; created_at: string; approved_by: string; actions: { title: string; status: string }[] } | null;

/** A proposed plan (tasks with owners and reasons) that a person approves onto the Workboard. */
export default function PlanPanel({ title, kind, subject, actions, investigation, onDone }: {
  title: string; kind: "absence" | "escalation"; subject: string; actions: PlanAction[];
  investigation: PlanInvestigation; onDone: () => void;
}) {
  const [msg, setMsg] = useState<string | null>(null);
  async function approve() {
    const c = credentials();
    if (!c) return;
    try {
      const r = await api<{ created: string[]; already_existed: string[] }>("/api/plans/approve", {
        method: "POST", write: true, body: JSON.stringify({ kind, subject_id: subject, approved_by: c.name }),
      });
      setMsg(`${r.created.length} tasks created, ${r.already_existed.length} already existed. They are on the Workboard.`);
      toast.success(r.created.length ? `Plan approved: ${r.created.length} tasks assigned` : "Plan already approved");
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) forgetPasscode();
      setMsg((e as Error).message);
    }
  }
  return (
    <section className="card flex flex-col">
      <div className="border-b border-line p-4">
        <div className="flex items-center gap-2 font-medium"><ClipboardCheck size={16} className="text-accent-hover" /> {title}</div>
        {investigation ? (
          <div className="mt-1 text-xs text-success">Approved by {investigation.approved_by} on {investigation.created_at.slice(0, 10)} ({investigation.id}).</div>
        ) : <div className="mt-1 text-xs text-muted">Proposed from the graph and company policy. Nothing is created until you approve.</div>}
      </div>
      <ol className="space-y-2 p-4">
        {actions.map((a, i) => (
          <li key={i} className="rounded-xl border border-line bg-elev p-3 text-sm">
            <div className="font-medium">{a.title}</div>
            <div className="mt-1 text-xs text-muted">{a.owner ?? "No owner found"} · {a.why}</div>
          </li>
        ))}
        {!actions.length && <li className="text-sm text-muted">Nothing to do.</li>}
      </ol>
      <div className="mt-auto border-t border-line p-4">
        <div className="flex gap-2">
          <button onClick={approve} disabled={!actions.length}
                  className="flex-1 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-40">
            {investigation ? "Approve again (no duplicates)" : "Approve plan"}
          </button>
          <Link href="/board" className="rounded-lg border border-line px-4 py-2 text-sm hover:border-line2">Workboard</Link>
        </div>
        {msg && <div className="mt-2 text-xs text-muted">{msg}</div>}
      </div>
    </section>
  );
}
