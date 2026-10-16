"use client";

import dagre from "@dagrejs/dagre";
import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useResolvedTheme } from "@/lib/theme";
import { api } from "@/lib/api";

type Org = {
  organizations: { id: string; name: string; kind: string; note: string; parent_id: string | null; officers: { id: string; name: string; role: string }[] }[];
  teams: { id: string; name: string; org_id: string; members: { id: string; name: string; role: string }[] }[];
  people: { id: string; name: string; role: string; team: string; team_id: string; open_work: number; away_now: boolean }[];
  reporting: { person: string; manager: string }[];
};
type Card = { title: string; sub: string; tone: string; away?: boolean; work?: number; id: string };

const W = 190, H = 58;

function OrgNode({ data }: NodeProps<Node<{ c: Card }>>) {
  const c = data.c;
  return (
    <div className={`rounded-xl border px-3 py-2 ${c.tone}`} style={{ width: W, height: H }}>
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <div className="flex items-center gap-1.5 truncate text-[13px] font-medium">{c.title}{c.away && <span className="rounded bg-warn/20 px-1 text-[9px] text-warn">away</span>}</div>
      <div className="truncate text-[11px] text-muted">{c.sub}{c.work ? ` · ${c.work} open` : ""}</div>
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </div>
  );
}
const nodeTypes = { org: OrgNode };

export default function OrgChart() {
  const theme = useResolvedTheme();
  const router = useRouter();
  const [o, setO] = useState<Org | null>(null);
  useEffect(() => { api<Org>("/api/org").then(setO); }, []);

  const flow = useMemo(() => {
    if (!o) return null;
    const cards: Card[] = [];
    const edges: [string, string][] = [];
    for (const org of o.organizations) {
      cards.push({ id: org.id, title: org.name, sub: org.kind, tone: "border-violet/50 bg-violet/15" });
      if (org.parent_id) edges.push([org.parent_id, org.id]);
      // Officers are people in the reporting tree below, so they are not drawn twice.
    }
    const managed = new Set(o.reporting.map((r) => r.person));
    for (const p of o.people) {
      const lead = p.team_id === "T-LEAD";
      cards.push({ id: p.id, title: p.name, sub: lead ? p.role : `${p.team}`, tone: p.away_now ? "border-warn/25 bg-warn/[0.07]" : lead ? "border-accent/25 bg-accent/[0.07]" : "border-line bg-panel", away: p.away_now, work: p.open_work });
      if (!managed.has(p.id)) edges.push(["ORG-FLYVI", p.id]);
    }
    for (const r of o.reporting) edges.push([r.manager, r.person]);
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "TB", nodesep: 18, ranksep: 46 });
    g.setDefaultEdgeLabel(() => ({}));
    cards.forEach((c) => g.setNode(c.id, { width: W, height: H }));
    edges.forEach(([a, b]) => g.setEdge(a, b));
    dagre.layout(g);
    const nodes: Node<{ c: Card }>[] = cards.map((c) => { const p = g.node(c.id); return { id: c.id, type: "org", position: { x: p.x - W / 2, y: p.y - H / 2 }, data: { c } }; });
    const es: Edge[] = edges.map(([a, b], i) => ({ id: `e${i}`, source: a, target: b, type: "smoothstep", style: { stroke: "var(--line2)" } }));
    return { nodes, es };
  }, [o]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="page-title">Organisation</h1>
        <p className="mt-1 text-sm text-muted">Datasol (Bangalore) Limited, Flyvi Technologies&apos; leadership and every reporting line, from the graph. Open work and who is away today are live. Click anyone for their full profile.</p>
      </div>
      <div className="card h-[72vh] overflow-hidden">
        {flow && (
          <ReactFlow nodes={flow.nodes} edges={flow.es} nodeTypes={nodeTypes} colorMode={theme} fitView minZoom={0.15} nodesDraggable={false}
                     onNodeClick={(_, n) => { const id = n.id.split("@")[0]; if (id.startsWith("P-")) router.push(`/people?id=${id}`); }}>
            <Background gap={22} color="var(--line)" />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
      </div>
      {o && (
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-4">
          {o.teams.filter((t) => t.members.length).map((t) => (
            <div key={t.id} className="card p-3 text-sm">
              <div className="font-medium">{t.name}</div>
              <div className="mt-1 text-xs text-muted">{t.members.map((m) => m.name).join(", ")}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
