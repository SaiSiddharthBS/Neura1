"use client";

import dagre from "@dagrejs/dagre";
import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { GraphEdge, GraphNode } from "@/lib/api";
import { useResolvedTheme } from "@/lib/theme";

const W = 184;
const H = 52;

const TYPE_STYLE: Record<string, string> = {
  part: "bg-elev border-ink",
  revision: "bg-elev border-line2",
  build: "bg-elev border-line2",
  order: "bg-elev border-line2",
  customer: "bg-elev border-line",
  person: "bg-accent/12 border-cyan/50 rounded-full",
  firmware: "bg-violet/12 border-violet/50",
  test: "bg-violet/12 border-violet/50",
  alternate: "bg-elev border-line2",
  decision: "bg-danger/20 border-danger text-ink",
  shipment: "bg-elev border-line",
};

const TYPE_LABEL: Record<string, string> = {
  part: "changed part", revision: "revision", build: "build", order: "customer order", customer: "customer",
  person: "owner", firmware: "firmware", test: "test procedure", alternate: "alternate", decision: "decision",
  shipment: "field units",
};

function statusClass(n: GraphNode): string {
  if (n.role === "changed") return "ring-2 ring-danger ring-offset-2";
  if (n.type === "revision" && n.applicable === false) return "opacity-50 border-dashed";
  if (n.type === "build" && n.at_risk) return "border-warn bg-warn/10";
  if (n.type === "order" && n.penalty) return "border-warn bg-warn/10";
  if (n.type === "alternate" && n.status === "rejected") return "border-danger bg-danger/10";
  if (n.type === "alternate" && n.status === "pending_review") return "border-warn bg-warn/10";
  return "";
}

function GraphCard({ data }: NodeProps<Node<{ n: GraphNode }>>) {
  const n = data.n;
  const sub =
    n.type === "revision" ? String(n.status ?? "") :
    n.type === "alternate" ? String(n.status ?? "").replace("_", " ") :
    n.type === "decision" ? `${n.outcome} · ${n.authority}` :
    n.type === "build" && n.at_risk ? `short ${n.shortfall}` :
    n.type === "order" && n.penalty ? "penalty clause" :
    TYPE_LABEL[n.type] ?? n.type;
  return (
    <div className={`border px-3 py-1.5 text-left shadow-sm ${n.type === "person" ? "" : "rounded-lg"} ${TYPE_STYLE[n.type] ?? "bg-elev border-line"} ${statusClass(n)}`}
         style={{ width: W, height: H }}>
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <div className="truncate text-[13px] font-medium leading-snug">{n.label}</div>
      <div className={`truncate text-[11px] leading-snug ${n.type === "decision" ? "text-muted" : "text-muted"}`}>{sub}</div>
      <Handle type="source" position={Position.Right} className="!opacity-0" />
    </div>
  );
}

const nodeTypes = { card: GraphCard };

export default function ImpactGraph({
  nodes, edges, onSelect,
}: { nodes: GraphNode[]; edges: GraphEdge[]; onSelect?: (n: GraphNode) => void }) {
  const theme = useResolvedTheme();
  const laid = useMemo(() => {
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "LR", nodesep: 16, ranksep: 64 });
    g.setDefaultEdgeLabel(() => ({}));
    nodes.forEach((n) => g.setNode(n.id, { width: W, height: H }));
    // Lay out outward from the changed part: most stored edges point toward it, so flip them.
    const directed = edges.map((e) => (e.label === "decided by" ? e : { ...e, source: e.target, target: e.source }));
    directed.forEach((e) => g.setEdge(e.source, e.target));
    dagre.layout(g);
    const rfNodes: Node<{ n: GraphNode }>[] = nodes.map((n) => {
      const p = g.node(n.id);
      return { id: n.id, type: "card", position: { x: p.x - W / 2, y: p.y - H / 2 }, data: { n } };
    });
    const rfEdges: Edge[] = directed.map((e, i) => ({
      id: `e${i}`, source: e.source, target: e.target, label: e.label,
      labelStyle: { fontSize: 10, fill: "var(--muted)" }, labelBgStyle: { fill: "var(--panel)" },
      style: { stroke: e.label === "rejected" ? "var(--danger)" : "var(--line2)" },
    }));
    return { rfNodes, rfEdges };
  }, [nodes, edges]);

  return (
    <ReactFlow
      nodes={laid.rfNodes}
      edges={laid.rfEdges}
      nodeTypes={nodeTypes}
      colorMode={theme}
      fitView
      fitViewOptions={{ padding: 0.08 }}
      minZoom={0.2}
      nodesDraggable={false}
      nodesConnectable={false}
      onNodeClick={(_, n) => onSelect?.(n.data.n as GraphNode)}
    >
      <Background gap={22} color="var(--line)" />
      <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-x-3 gap-y-1 rounded-md bg-panel/90 px-2 py-1 text-[11px] text-muted ring-1 ring-line">
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full ring-2 ring-danger" />changed part</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm border border-dashed border-line2" />excluded revision</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-warn/40" />at risk</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-danger/40" />rejected</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-cyan/40" />owner</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-violet/40" />firmware / test</span>
      </div>
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
