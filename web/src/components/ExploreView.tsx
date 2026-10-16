"use client";

import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps, type ReactFlowInstance } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useRouter, useSearchParams } from "next/navigation";
import { Clock, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import { api } from "@/lib/api";

type GNode = { id: string; label: string; name: string; kind?: string };
type GEdge = { source: string; target: string; label: string };
type Event = { at: string; kind: string; title: string; detail: string; ref: string };
type Hit = { id: string; label: string; name: string };

const TONE: Record<string, string> = {
  Item: "border-cyan/50 bg-cyan/10", Revision: "border-line2 bg-elev", Person: "border-accent/50 bg-accent/10",
  Project: "border-violet/50 bg-violet/10", Customer: "border-warn/50 bg-warn/10", Order: "border-warn/40 bg-warn/5",
  Build: "border-line2 bg-elev", Decision: "border-danger/50 bg-danger/10", Source: "border-line bg-panel",
  Action: "border-success/40 bg-success/10", Quote: "border-line2 bg-elev", Team: "border-accent/30 bg-accent/5",
  Investigation: "border-success/40 bg-success/5", Skill: "border-violet/30 bg-violet/5",
};
const W = 170, H = 50;

function Card({ data }: NodeProps<Node<{ n: GNode; center: boolean }>>) {
  const { n, center } = data;
  return (
    <div className="rounded-xl bg-[#0b1020]">
    <div className={`relative z-10 rounded-xl border px-3 py-1.5 ${TONE[n.label] ?? "border-line bg-panel"} ${center ? "ring-2 ring-cyan ring-offset-2 ring-offset-transparent" : ""}`} style={{ width: W, height: H }}>
      <Handle type="target" position={Position.Top} className="!opacity-0" style={{ left: "50%", top: "50%", transform: "translate(-50%,-50%)" }} />
      <div className="truncate text-[12px] font-medium">{n.label === "Person" || n.label === "Source" || n.label === "Project" || n.label === "Customer" ? n.name : n.id}</div>
      <div className="truncate text-[10.5px] text-muted">{n.label}{n.name && n.name !== n.id && !["Person", "Source", "Project", "Customer"].includes(n.label) ? ` · ${n.name}` : ""}</div>
      <Handle type="source" position={Position.Bottom} className="!opacity-0" style={{ left: "50%", top: "50%", transform: "translate(-50%,-50%)" }} />
    </div>
    </div>
  );
}
const nodeTypes = { card: Card };

export default function ExploreView() {
  const params = useSearchParams();
  const router = useRouter();
  const start = params.get("id") ?? "NB54360";
  const [nodes, setNodes] = useState<Map<string, GNode>>(new Map());
  const [pos, setPos] = useState<Map<string, { x: number; y: number }>>(new Map());
  const [edges, setEdges] = useState<GEdge[]>([]);
  const [focus, setFocus] = useState(start);
  const [events, setEvents] = useState<Event[]>([]);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const rf = useRef<ReactFlowInstance<Node<{ n: GNode; center: boolean }>, Edge> | null>(null);

  const expand = useCallback(async (id: string, reset = false) => {
    const g = await api<{ nodes: GNode[]; edges: GEdge[] }>(`/api/explore?id=${encodeURIComponent(id)}`);
    setNodes((m) => { const next = reset ? new Map<string, GNode>() : new Map(m); g.nodes.forEach((n) => next.set(n.id, n)); return next; });
    // Mind-map layout: neighbours fan out in columns beside the record that was opened, grouped by kind.
    setPos((m) => {
      const next = reset ? new Map<string, { x: number; y: number }>() : new Map(m);
      const c = next.get(id) ?? { x: 0, y: 0 };
      next.set(id, c);
      const fresh = g.nodes.filter((n) => !next.has(n.id)).sort((a, b) => a.label.localeCompare(b.label) || a.name.localeCompare(b.name));
      const sides: [number, typeof fresh][] = c.x === 0 && c.y === 0
        ? [[-1, fresh.slice(0, Math.ceil(fresh.length / 2))], [1, fresh.slice(Math.ceil(fresh.length / 2))]]
        : [[c.x < 0 ? -1 : 1, fresh]];
      for (const [dir, list] of sides) {
        list.forEach((n, i) => {
          const dy = (i - (list.length - 1) / 2) * (H + 14);
          next.set(n.id, { x: c.x + dir * (W + 150 - Math.abs(dy) * 0.12), y: c.y + dy });
        });
      }
      return next;
    });
    setEdges((e) => { const all = reset ? g.edges : [...e, ...g.edges]; const k = new Set<string>(); return all.filter((x) => { const s = `${x.source}|${x.target}|${x.label}`; if (k.has(s)) return false; k.add(s); return true; }); });
    setFocus(id);
    setTimeout(() => rf.current?.fitView({ padding: 0.08, duration: 400 }), 60);
    api<Event[]>(`/api/timeline?id=${encodeURIComponent(id)}`).then(setEvents);
  }, []);

  useEffect(() => { setTimeout(() => expand(start, true), 0); }, [start, expand]);
  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(() => api<Hit[]>(`/api/lookup?q=${encodeURIComponent(q)}`).then(setHits), 150);
    return () => clearTimeout(t);
  }, [q]);

  const flow = useMemo(() => {
    const rf: Node<{ n: GNode; center: boolean }>[] = [...nodes.values()].map((n) => {
      const p = pos.get(n.id) ?? { x: 0, y: 0 };
      return { id: n.id, type: "card", position: { x: p.x - W / 2, y: p.y - H / 2 }, data: { n, center: n.id === focus } };
    });
    const re: Edge[] = edges.filter((e) => nodes.has(e.source) && nodes.has(e.target)).map((e, i) => ({
      id: `e${i}`, type: "straight", source: e.source, target: e.target, label: e.label.toLowerCase().replaceAll("_", " "),
      labelStyle: { fontSize: 9, fill: "rgba(226,233,245,0.55)" }, labelBgStyle: { fill: "#0b1020" },
      style: { stroke: "rgba(148,163,184,0.35)" },
    }));
    return { rf, re };
  }, [nodes, edges, focus, pos]);

  const focused = nodes.get(focus);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Graph explorer</h1>
          <p className="mt-1 text-sm text-muted">Walk Flyvi&apos;s company graph live from FalkorDB. Click any record to expand its connections and see its history.</p>
        </div>
        <div className="relative w-80">
          <div className="flex items-center gap-2 rounded-xl border border-line bg-elev px-3">
            <Search size={14} className="text-muted" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Start from a part, person, project…" className="h-10 flex-1 bg-transparent text-sm outline-none" style={{ background: "transparent" }} />
          </div>
          {q.length >= 2 && hits.length > 0 && (
            <div className="card absolute right-0 top-12 z-20 w-full p-1">
              {hits.map((h) => (
                <button key={h.id} onClick={() => { setQ(""); setHits([]); router.replace(`/explore?id=${encodeURIComponent(h.id)}`); }}
                        className="block w-full truncate rounded-lg px-3 py-1.5 text-left text-sm hover:bg-elev">{h.name} <span className="text-xs text-muted">· {h.label}</span></button>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <div className="card h-[72vh] overflow-hidden">
          <ReactFlow key={start} onInit={(i) => { rf.current = i; }} fitViewOptions={{ padding: 0.08 }} nodes={flow.rf} edges={flow.re} nodeTypes={nodeTypes} colorMode="dark" fitView minZoom={0.1} nodesDraggable
                     onNodeClick={(_, n) => expand(n.id)}>
            <Background gap={22} color="rgba(255,255,255,0.05)" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <aside className="card flex h-[72vh] flex-col">
          <div className="border-b border-line p-4">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-muted"><Clock size={12} /> History</div>
            <div className="mt-1 font-medium">{focused?.name ?? focus}</div>
            <div className="text-xs text-muted">{focused?.label} · {nodes.size} records on screen</div>
          </div>
          <ol className="flex-1 space-y-3 overflow-y-auto p-4">
            {events.map((e, i) => (
              <li key={i} className="relative border-l border-line pl-4">
                <span className="absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full bg-accent" />
                <div className="text-[11px] text-muted">{e.at.slice(0, 10)} · {e.kind}</div>
                <button onClick={() => e.ref?.includes("#") && setOpen(e.ref)} className="text-left text-sm font-medium hover:underline">{e.title}</button>
                <div className="line-clamp-3 text-xs text-muted">{e.detail}</div>
              </li>
            ))}
            {!events.length && <li className="text-sm text-muted">No dated history for this record.</li>}
          </ol>
        </aside>
      </div>
      {open && <EvidenceDrawer key={open} chunk={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
