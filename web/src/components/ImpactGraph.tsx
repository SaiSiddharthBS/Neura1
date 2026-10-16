"use client";

import dagre from "@dagrejs/dagre";
import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { GraphEdge, GraphNode } from "@/lib/api";

const W = 184;
const H = 52;

const TYPE_STYLE: Record<string, string> = {
  part: "bg-white border-ink",
  revision: "bg-white border-slate-400",
  build: "bg-white border-slate-400",
  order: "bg-white border-slate-400",
  customer: "bg-slate-50 border-slate-300",
  person: "bg-teal-50 border-teal-300 rounded-full",
  firmware: "bg-indigo-50 border-indigo-300",
  test: "bg-indigo-50 border-indigo-300",
  alternate: "bg-white border-slate-400",
  decision: "bg-ink border-ink text-white",
  shipment: "bg-slate-50 border-slate-300",
};

const TYPE_LABEL: Record<string, string> = {
  part: "changed part", revision: "revision", build: "build", order: "customer order", customer: "customer",
  person: "owner", firmware: "firmware", test: "test procedure", alternate: "alternate", decision: "decision",
  shipment: "field units",
};

function statusClass(n: GraphNode): string {
  if (n.role === "changed") return "ring-2 ring-danger ring-offset-2";
  if (n.type === "revision" && n.applicable === false) return "opacity-50 border-dashed";
  if (n.type === "build" && n.at_risk) return "border-warn bg-amber-50";
  if (n.type === "order" && n.penalty) return "border-warn bg-amber-50";
  if (n.type === "alternate" && n.status === "rejected") return "border-danger bg-red-50";
  if (n.type === "alternate" && n.status === "pending_review") return "border-warn bg-amber-50";
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
    <div className={`border px-3 py-1.5 text-left shadow-sm ${n.type === "person" ? "" : "rounded-lg"} ${TYPE_STYLE[n.type] ?? "bg-white border-slate-300"} ${statusClass(n)}`}
         style={{ width: W, height: H }}>
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <div className="truncate text-[13px] font-medium leading-snug">{n.label}</div>
      <div className={`truncate text-[11px] leading-snug ${n.type === "decision" ? "text-white/70" : "text-muted"}`}>{sub}</div>
      <Handle type="source" position={Position.Right} className="!opacity-0" />
    </div>
  );
}

const nodeTypes = { card: GraphCard };

export default function ImpactGraph({
  nodes, edges, onSelect,
}: { nodes: GraphNode[]; edges: GraphEdge[]; onSelect?: (n: GraphNode) => void }) {
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
      labelStyle: { fontSize: 10, fill: "#6b7280" }, labelBgStyle: { fill: "#f6f7f9" },
      style: { stroke: e.label === "rejected" ? "#b91c1c" : "#cbd5e1" },
    }));
    return { rfNodes, rfEdges };
  }, [nodes, edges]);

  return (
    <ReactFlow
      nodes={laid.rfNodes}
      edges={laid.rfEdges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.08 }}
      minZoom={0.2}
      nodesDraggable={false}
      nodesConnectable={false}
      onNodeClick={(_, n) => onSelect?.(n.data.n as GraphNode)}
    >
      <Background gap={20} color="#e5e7eb" />
      <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-x-3 gap-y-1 rounded-md bg-panel/90 px-2 py-1 text-[11px] text-muted ring-1 ring-line">
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full ring-2 ring-danger" />changed part</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm border border-dashed border-slate-400" />excluded revision</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-amber-200" />at risk</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-red-200" />rejected</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-teal-200" />owner</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-indigo-200" />firmware / test</span>
      </div>
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
