"use client";

import { Loader2, RotateCcw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";

/** Put the demo company back to where the story starts (records, documents, verified extractions, skill tags). */
export default function ResetDemo() {
  const [stage, setStage] = useState<"idle" | "confirm" | "running">("idle");

  async function reset() {
    if (!credentials()) return;
    setStage("running");
    try {
      await api("/api/admin/reset", { method: "POST", write: true });
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const s = await api<{ running: boolean; error: string | null }>("/api/admin/reset");
        if (!s.running) {
          if (s.error) throw new Error(s.error);
          toast.success("The demo company is back to the start", { description: "Reload any open page to see it." });
          break;
        }
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) forgetPasscode();
      toast.error("Reset failed", { description: (e as Error).message });
    } finally { setStage("idle"); }
  }

  return (
    <div className="card p-4">
      <div className="text-[14px] font-semibold tracking-tight">Reset the demo company</div>
      <p className="mt-1 text-[13px] text-muted">Rebuild Flyvi from its fixture: records, documents, verified extractions and skill tags. Plans, tasks, chat and documents added since are cleared.</p>
      {stage === "confirm" ? (
        <div className="mt-3 flex gap-2">
          <button onClick={reset} className="rounded-lg bg-danger px-3 py-1.5 text-[13px] font-medium text-white hover:opacity-90">Yes, reset everything</button>
          <button onClick={() => setStage("idle")} className="rounded-lg border border-line px-3 py-1.5 text-[13px] hover:border-line2">Cancel</button>
        </div>
      ) : (
        <button onClick={() => setStage("confirm")} disabled={stage === "running"}
                className="mt-3 flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[13px] hover:border-line2 disabled:opacity-50">
          {stage === "running" ? <Loader2 size={13} className="animate-spin" /> : <RotateCcw size={13} />} {stage === "running" ? "Rebuilding…" : "Reset"}
        </button>
      )}
    </div>
  );
}
