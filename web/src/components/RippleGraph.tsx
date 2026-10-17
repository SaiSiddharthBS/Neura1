"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, RotateCcw, Waves } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type GNode = { id: string; type: string; label: string; name?: string; role?: string };
type GEdge = { source: string; target: string; label: string };
type Impact = { status: string; part: { id: string; name: string }; graph: { nodes: GNode[]; edges: GEdge[] } };

const NOTICE = "inbox/notice_NB54360_2026-10-14.md";
const W = 1000, H = 580, CX = W / 2, CY = H / 2;
// Ring spacing: inner rings get more room than a linear spacing would give them, so labels near the centre breathe.
const ringScale = (l: number, max: number) => 0.24 + 0.76 * Math.pow(l / max, 0.85);
const STEP = 0.55; // seconds between rings

// What each kind of record is, in the order a change travels.
const KIND: Record<string, { label: string; color: string }> = {
  part: { label: "changed part", color: "var(--accent)" },
  revision: { label: "product revisions", color: "var(--cyan)" },
  build: { label: "builds", color: "var(--warn)" },
  order: { label: "customer orders", color: "var(--violet)" },
  customer: { label: "customers", color: "var(--danger)" },
  person: { label: "people", color: "var(--ink-soft)" },
  decision: { label: "past decisions", color: "var(--danger)" },
  alternate: { label: "alternates", color: "var(--faint)" },
  shipment: { label: "units in the field", color: "var(--warn)" },
  firmware: { label: "firmware", color: "var(--success)" },
  test: { label: "test procedures", color: "var(--success)" },
};
const colorOf = (t: string) => KIND[t]?.color ?? "var(--muted)";

/** Lay the records out in rings by distance from the changed part, keeping each record near what led to it. */
function layout(nodes: GNode[], edges: GEdge[], center: string) {
  const adj = new Map<string, Set<string>>();
  for (const e of edges) {
    if (!adj.has(e.source)) adj.set(e.source, new Set());
    if (!adj.has(e.target)) adj.set(e.target, new Set());
    adj.get(e.source)!.add(e.target);
    adj.get(e.target)!.add(e.source);
  }
  const level = new Map<string, number>([[center, 0]]);
  const parents = new Map<string, string[]>();
  let frontier = [center];
  while (frontier.length) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const n of adj.get(id) ?? []) {
        if (!level.has(n)) { level.set(n, level.get(id)! + 1); next.push(n); parents.set(n, [id]); }
        else if (level.get(n) === level.get(id)! + 1) parents.get(n)!.push(id);
      }
    }
    frontier = next;
  }
  const maxLevel = Math.max(1, ...level.values());
  const angle = new Map<string, number>([[center, 0]]);
  const pos = new Map<string, { x: number; y: number }>([[center, { x: CX, y: CY }]]);
  for (let l = 1; l <= maxLevel; l++) {
    const ring = nodes.filter((n) => level.get(n.id) === l).map((n) => {
      const ps = parents.get(n.id) ?? [];
      const want = l === 1 ? 0 : ps.reduce((a, p) => a + (angle.get(p) ?? 0), 0) / Math.max(ps.length, 1);
      return { id: n.id, want };
    }).sort((a, b) => a.want - b.want || a.id.localeCompare(b.id));
    const offset = l === 1 ? -Math.PI / 2 : (ring[0]?.want ?? 0) - Math.PI / ring.length;
    ring.forEach((r, i) => {
      const a = l === 1 ? offset + (2 * Math.PI * i) / ring.length : offset + (2 * Math.PI * (i + 0.5)) / ring.length;
      angle.set(r.id, a);
      const k = ringScale(l, maxLevel);
      const rx = k * (W / 2 - 80), ry = k * (H / 2 - 40);
      pos.set(r.id, { x: CX + rx * Math.cos(a), y: CY + ry * Math.sin(a) });
    });
  }
  return { level, pos, maxLevel };
}

export default function RippleGraph() {
  const router = useRouter();
  const reduce = useReducedMotion();
  const [r, setR] = useState<Impact | null>(null);
  const [error, setError] = useState(false);
  const [run, setRun] = useState(0);
  const [hover, setHover] = useState<GNode | null>(null);

  useEffect(() => {
    api<Impact>(`/api/impact/notice?source_id=${encodeURIComponent(NOTICE)}`, { method: "POST" })
      .then((x) => (x.status === "ok" ? setR(x) : setError(true))).catch(() => setError(true));
  }, []);

  const g = useMemo(() => (r ? layout(r.graph.nodes, r.graph.edges, r.part.id) : null), [r]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    r?.graph.nodes.forEach((n) => { c[n.type] = (c[n.type] ?? 0) + 1; });
    return c;
  }, [r]);
  const delay = (l: number) => (reduce ? 0 : 0.35 + l * STEP);

  if (error) return null;
  return (
    <section data-tour="ripple" className="card no-reveal overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
        <div>
          <div className="flex items-center gap-2 text-[14px] font-semibold tracking-tight"><Waves size={15} className="text-accent" /> Watch one change ripple through Flyvi</div>
          <p className="mt-0.5 text-[13px] text-muted">
            {r ? <>A supplier raised the price and lead time of <span className="font-mono text-ink">{r.part.id}</span>. One FalkorDB traversal follows it through the company, ring by ring.</> : "Tracing the change through the company graph…"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setRun((x) => x + 1)} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12.5px] text-muted hover:border-line2 hover:text-ink">
            <RotateCcw size={13} /> Replay</button>
          <Link href={`/impact?source=${encodeURIComponent(NOTICE)}`} className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-[12.5px] font-medium text-accent-ink hover:bg-accent-hover">
            Open the impact <ArrowRight size={13} /></Link>
        </div>
      </div>

      <div className="relative">
        {!g && <div className="m-5 skeleton h-[300px]" />}
        {g && r && (
          <svg key={run} viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img"
               aria-label={`Impact of the ${r.part.id} change across ${r.graph.nodes.length} records`}>
            {Array.from({ length: g.maxLevel }).map((_, i) => (
              <motion.ellipse key={`ring${i}`} cx={CX} cy={CY} rx={ringScale(i + 1, g.maxLevel) * (W / 2 - 80)} ry={ringScale(i + 1, g.maxLevel) * (H / 2 - 40)}
                              fill="none" style={{ stroke: "var(--line)" }} strokeDasharray="2 6"
                              initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: delay(i + 1) - 0.2, duration: 0.6 }} />
            ))}
            {!reduce && [0, 1, 2].map((i) => (
              <motion.ellipse key={`pulse${i}`} cx={CX} cy={CY} fill="none" style={{ stroke: "var(--accent)" }} strokeWidth={1.5}
                              initial={{ rx: 8, ry: 8, opacity: 0.6 }} animate={{ rx: W / 2 - 60, ry: H / 2 - 30, opacity: 0 }}
                              transition={{ duration: 3.2, delay: i * 1.05, repeat: Infinity, ease: "easeOut" }} />
            ))}
            {r.graph.edges.map((e, i) => {
              const a = g.pos.get(e.source), b = g.pos.get(e.target);
              if (!a || !b) return null;
              const l = Math.max(g.level.get(e.source) ?? 0, g.level.get(e.target) ?? 0);
              const hot = hover && (hover.id === e.source || hover.id === e.target);
              return (
                <motion.line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeWidth={hot ? 1.8 : 1}
                             style={{ stroke: hot ? "var(--accent)" : "var(--line2)" }}
                             initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: 1 }}
                             transition={{ delay: delay(l) - 0.3, duration: 0.45, ease: [0.16, 1, 0.3, 1] }} />
              );
            })}
            {r.graph.nodes.map((n) => {
              const p = g.pos.get(n.id);
              if (!p) return null;
              const l = g.level.get(n.id) ?? 0;
              const center = l === 0;
              return (
                <g key={n.id} transform={`translate(${p.x} ${p.y})`}>
                <motion.g style={{ cursor: "pointer" }} onMouseEnter={() => setHover(n)} onMouseLeave={() => setHover(null)}
                          onClick={() => router.push(`/explore?id=${encodeURIComponent(n.id)}`)}
                          initial={{ opacity: 0, scale: 0.3 }} animate={{ opacity: 1, scale: 1 }}
                          transition={{ delay: delay(l), type: "spring", stiffness: 260, damping: 18 }}>
                  {center && <circle r={26} style={{ fill: "var(--accent)", opacity: 0.18 }} />}
                  <circle r={center ? 15 : 7} style={{ fill: colorOf(n.type), stroke: "var(--panel)" }} strokeWidth={2} />
                  <text y={center ? 34 : 20} textAnchor="middle" className="font-mono" style={{ fill: center ? "var(--ink)" : "var(--muted)", fontSize: center ? 15 : 10.5, paintOrder: "stroke", stroke: "var(--panel)", strokeWidth: 3 }}>
                    {n.label.length > 16 ? n.label.slice(0, 15) + "…" : n.label}
                  </text>
                </motion.g>
                </g>
              );
            })}
          </svg>
        )}
        <AnimatePresence>
          {hover && (
            <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                        className="surface-pop pointer-events-none absolute left-4 top-3 max-w-xs px-3 py-2 text-[12.5px]">
              <div className="font-medium">{hover.label}</div>
              <div className="text-muted">{KIND[hover.type]?.label ?? hover.type}{hover.name && hover.name !== hover.label ? ` · ${hover.name}` : ""}</div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {r && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-line px-5 py-3 text-[12px] text-muted">
          {["part", "revision", "build", "order", "customer", "person", "decision"].filter((t) => counts[t]).map((t, i) => (
            <motion.span key={t} className="flex items-center gap-1.5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: delay(i) }}>
              <span className="h-2 w-2 rounded-full" style={{ background: colorOf(t) }} />
              <span className="num font-semibold text-ink">{counts[t]}</span> {KIND[t].label}
            </motion.span>
          ))}
          <span className="ml-auto text-faint">Click any record to explore it</span>
        </div>
      )}
    </section>
  );
}
