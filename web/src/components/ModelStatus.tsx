"use client";

import { Cpu } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Health = { model?: string; where?: string; on_fallback?: boolean };

/** Which model is answering right now: the DGX Spark, or this machine's fallback while the DGX is out of reach. */
export default function ModelStatus() {
  const [h, setH] = useState<Health | null>(null);
  useEffect(() => {
    const load = () => api<Health>("/api/health").then(setH).catch(() => setH(null));
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);
  if (!h?.model) return null;
  const name = h.model.replace(/-\d+(\.\d+)?b(-a\d+b)?$/i, "");
  return (
    <span title={`${h.model} on ${h.where}${h.on_fallback ? " (main model unreachable)" : ""}`}
          className="flex min-w-0 items-center gap-1.5 text-[11px] text-faint">
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${h.on_fallback ? "bg-warn" : "bg-success"}`} />
      <Cpu size={11} className="shrink-0" />
      <span className="truncate">{name} · {h.on_fallback ? "fallback" : h.where}</span>
    </span>
  );
}
