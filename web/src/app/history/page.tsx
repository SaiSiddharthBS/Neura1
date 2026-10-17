"use client";

import { PageTitle } from "@/components/ui";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, inr } from "@/lib/api";

type Inv = { id: string; item: string; source: string | null; source_title: string | null; created_at: string;
             approved_by: string; cost_total: string | null; currency: string | null; actions: number };

export default function History() {
  const [rows, setRows] = useState<Inv[] | null>(null);
  useEffect(() => { api<Inv[]>("/api/investigations").then(setRows); }, []);
  return (
    <div>
      <PageTitle>Plans, <em>remembered</em></PageTitle>
      <p className="mt-1 text-sm text-muted">Approved investigations and the tasks they created, stored in the graph.</p>
      <div className="card mt-4 divide-y divide-line">
        {rows?.length === 0 && <div className="p-4 text-sm text-muted">Nothing approved yet.</div>}
        {rows?.map((r) => (
          <Link key={r.id} href={r.source ? `/impact?source=${encodeURIComponent(r.source)}` : `/impact?item=${r.item}`}
                className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm hover:bg-bg">
            <div>
              <div className="font-medium">{r.item} · {r.source_title ?? "what-if"}</div>
              <div className="text-xs text-muted">{r.id} · approved by {r.approved_by} · {r.created_at.replace("T", " ").slice(0, 16)} UTC</div>
            </div>
            <div className="text-right">
              <div>{r.actions} tasks</div>
              <div className="text-xs text-muted">{r.cost_total ? inr(r.cost_total, r.currency ?? "INR") : ""}</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
