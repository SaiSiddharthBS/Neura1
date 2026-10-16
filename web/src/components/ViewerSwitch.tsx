"use client";

import { Eye } from "lucide-react";
import { useEffect, useState } from "react";
import { api, viewerId } from "@/lib/api";

type P = { id: string; name: string; role: string; team: string };

/** Who the brain is acting for. Money and leave details follow this person's place in the graph. */
export default function ViewerSwitch() {
  const [people, setPeople] = useState<P[]>([]);
  const [me, setMe] = useState("P-HITHESH");
  useEffect(() => {
    setTimeout(() => setMe(viewerId()), 0);
    api<P[]>("/api/people").then((x) => setPeople(x.filter((p) => p.team !== "Board")));
  }, []);
  return (
    <label className="block rounded-xl bg-elev px-3 py-2 text-xs text-muted">
      <span className="mb-1 flex items-center gap-1.5"><Eye size={12} /> Viewing as</span>
      <select value={me} onChange={(e) => { try { localStorage.setItem("neura1-viewer", e.target.value); } catch {} location.reload(); }}
              className="w-full rounded-md border border-line px-2 py-1 text-[13px] text-ink">
        {people.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.role}</option>)}
      </select>
    </label>
  );
}
