"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";
import { ArrowRight, ArrowUpRight, RotateCcw, Waves, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";

export type GNode = { id: string; type: string; label: string; name?: string; role?: string };
export type GEdge = { source: string; target: string; label: string };
export type Impact = { status: string; part: { id: string; name: string }; graph: { nodes: GNode[]; edges: GEdge[] } };

export const NOTICE = "inbox/notice_NB54360_2026-10-14.md";
const W = 1000, H = 580, CX = W / 2, CY = H / 2;
// Ring spacing: inner rings get more room than a linear spacing would give them, so labels near the centre breathe.
const ringScale = (l: number, max: number) => 0.24 + 0.76 * Math.pow(l / max, 0.85);
const STEP = 0.5; // seconds between rings
const EASE = [0.16, 1, 0.3, 1] as const;

// What each kind of record is, in the order a change travels.
export const KIND: Record<string, { label: string; color: string }> = {
  part: { label: "changed part", color: "var(--accent)" },
  revision: { label: "product revision", color: "var(--cyan)" },
  build: { label: "planned build", color: "var(--warn)" },
  order: { label: "customer order", color: "var(--violet)" },
  customer: { label: "customer", color: "var(--danger)" },
  person: { label: "person", color: "var(--ink-soft)" },
  decision: { label: "past decision", color: "var(--danger)" },
  alternate: { label: "alternate part", color: "var(--faint)" },
  shipment: { label: "units in the field", color: "var(--warn)" },
  firmware: { label: "firmware", color: "var(--success)" },
  test: { label: "test procedure", color: "var(--success)" },
};
export const LEGEND: Record<string, string> = { part: "changed part", revision: "product revisions", build: "builds", order: "customer orders",
  customer: "customers", person: "people", decision: "past decisions" };
const colorOf = (t: string) => KIND[t]?.color ?? "var(--muted)";
const PLURAL: Record<string, string> = { person: "people", shipment: "batches of units in the field", firmware: "firmware modules" };

/** Lay the records out in rings by distance from the changed part, keeping each record near what led to it. */
export function layout(nodes: GNode[], edges: GEdge[], center: string) {
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
  const children = new Map<string, string[]>();
  for (const [c, ps] of parents) for (const p of ps) children.set(p, [...(children.get(p) ?? []), c]);
  return { level, pos, maxLevel, parents, children };
}

/** A gentle curve from a to b that bows away from the centre, so connections read as flowing outward. */
function curve(a: { x: number; y: number }, b: { x: number; y: number }) {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  const dx = mx - CX, dy = my - CY, d = Math.hypot(dx, dy) || 1;
  const bow = Math.min(36, Math.hypot(b.x - a.x, b.y - a.y) * 0.16);
  return `M ${a.x.toFixed(1)} ${a.y.toFixed(1)} Q ${(mx + (dx / d) * bow).toFixed(1)} ${(my + (dy / d) * bow).toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
}

// ---------- labels that never overlap ----------

const CHAR = 6.3; // Geist Mono at 10.5px
const short = (s: string) => (s.length > 16 ? s.slice(0, 15) + "…" : s);
type Label = { x: number; y: number; anchor: "start" | "middle" | "end"; fits: boolean };
type Box = [number, number, number, number];
const hits = (a: Box, b: Box) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
const PRIORITY: Record<string, number> = { customer: 0, order: 1, build: 2, revision: 3, decision: 4, person: 5 };

/** Ease records apart along their ring where two would touch, so dots and names have room. */
function relax(pos: Map<string, { x: number; y: number }>, level: Map<string, number>, maxLevel: number) {
  const ids = [...pos.keys()].filter((id) => (level.get(id) ?? 0) > 0);
  const ang = new Map(ids.map((id) => {
    const p = pos.get(id)!, k = ringScale(level.get(id)!, maxLevel);
    return [id, Math.atan2((p.y - CY) / (k * (H / 2 - 40)), (p.x - CX) / (k * (W / 2 - 80)))];
  }));
  const at = (id: string) => {
    const k = ringScale(level.get(id)!, maxLevel), a = ang.get(id)!;
    return { x: CX + k * (W / 2 - 80) * Math.cos(a), y: CY + k * (H / 2 - 40) * Math.sin(a) };
  };
  for (let it = 0; it < 60; it++) {
    let moved = false;
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
      const a = at(ids[i]), b = at(ids[j]);
      if (Math.hypot(a.x - b.x, a.y - b.y) >= 30) continue;
      // Turn each along its own ring, away from the other.
      const da = Math.atan2(a.y - CY, a.x - CX) - Math.atan2(b.y - CY, b.x - CX);
      const s = Math.sign(Math.sin(da)) || 1;
      ang.set(ids[i], ang.get(ids[i])! + 0.018 * s);
      ang.set(ids[j], ang.get(ids[j])! - 0.018 * s);
      moved = true;
    }
    if (!moved) break;
  }
  return new Map([...pos].map(([id, p]) => [id, (level.get(id) ?? 0) > 0 ? at(id) : p]));
}

function placeLabels(nodes: GNode[], pos: Map<string, { x: number; y: number }>, level: Map<string, number>) {
  const taken: Box[] = [[CX - 44, CY - 44, CX + 44, CY + 66]]; // the orb and its name
  for (const n of nodes) {
    const p = pos.get(n.id);
    if (p && (level.get(n.id) ?? 0) > 0) taken.push([p.x - 9, p.y - 9, p.x + 9, p.y + 9]);
  }
  const out = new Map<string, Label>();
  const order = nodes.filter((n) => (level.get(n.id) ?? 0) > 0)
    .sort((a, b) => (level.get(a.id)! - level.get(b.id)!) || ((PRIORITY[a.type] ?? 9) - (PRIORITY[b.type] ?? 9)));
  for (const n of order) {
    const p = pos.get(n.id)!;
    const w = short(n.label).length * CHAR;
    const dx = (p.x - CX) / (W / 2), dy = (p.y - CY) / (H / 2);
    const right: Label & { box: Box } = { x: p.x + 12, y: p.y + 3.5, anchor: "start", fits: true, box: [p.x + 11, p.y - 7, p.x + 13 + w, p.y + 6] };
    const left: Label & { box: Box } = { x: p.x - 12, y: p.y + 3.5, anchor: "end", fits: true, box: [p.x - 13 - w, p.y - 7, p.x - 11, p.y + 6] };
    const below: Label & { box: Box } = { x: p.x, y: p.y + 20, anchor: "middle", fits: true, box: [p.x - w / 2 - 1, p.y + 11, p.x + w / 2 + 1, p.y + 23] };
    const above: Label & { box: Box } = { x: p.x, y: p.y - 13, anchor: "middle", fits: true, box: [p.x - w / 2 - 1, p.y - 23, p.x + w / 2 + 1, p.y - 10] };
    const outward = Math.abs(dx) > Math.abs(dy) * 0.9 ? (dx > 0 ? [right, below, above, left] : [left, below, above, right])
      : dy > 0 ? [below, dx > 0 ? right : left, dx > 0 ? left : right, above] : [above, dx > 0 ? right : left, dx > 0 ? left : right, below];
    const inside = (b: Box) => b[0] > 4 && b[2] < W - 4 && b[1] > 4 && b[3] < H - 4;
    const ok = outward.find((c) => inside(c.box) && !taken.some((t) => hits(t, c.box)));
    if (ok) taken.push(ok.box);
    const pick = ok ?? outward[0];
    out.set(n.id, { x: pick.x, y: pick.y, anchor: pick.anchor, fits: !!ok });
  }
  return out;
}

/** Four soft lights on slow, different orbits: inside the glass they blend like liquid; blurred, they are the halo. */
function OrbLight({ reduce, spread }: { reduce: boolean; spread: number }) {
  const lights = [
    { color: "#3b82f6", r: 15, at: [6, -3], dur: 9, dir: 1 },
    { color: "#22d3ee", r: 12, at: [-7, 5], dur: 12, dir: -1 },
    { color: "#a78bfa", r: 13, at: [3, 8], dur: 7.5, dir: 1 },
    { color: "#f472b6", r: 9, at: [-5, -7], dur: 10.5, dir: -1 },
  ];
  return (
    <>
      {lights.map((l, i) => (
        <g key={i}>
          {!reduce && <animateTransform attributeName="transform" type="rotate" from={l.dir > 0 ? "0" : "360"} to={l.dir > 0 ? "360" : "0"}
                                        dur={`${l.dur}s`} repeatCount="indefinite" />}
          <circle cx={l.at[0] * spread} cy={l.at[1] * spread} r={l.r * spread} fill={l.color} opacity={0.9}>
            {!reduce && <animate attributeName="r" values={`${l.r * spread};${l.r * spread * 1.22};${l.r * spread}`} dur={`${(l.dur * 0.55).toFixed(1)}s`}
                                 repeatCount="indefinite" calcMode="spline" keyTimes="0;0.5;1" keySplines="0.45 0 0.55 1;0.45 0 0.55 1" />}
          </circle>
        </g>
      ))}
    </>
  );
}

export default function RippleGraph() {
  const router = useRouter();
  const reduce = useReducedMotion();
  const [r, setR] = useState<Impact | null>(null);
  const [error, setError] = useState(false);
  const [run, setRun] = useState(0);
  const [hover, setHover] = useState<string | null>(null);
  const [ring, setRing] = useState<number | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [spot, setSpot] = useState<{ x: number; y: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  // The map leans a few degrees towards the pointer, on a soft spring, so it feels like an object in space.
  const px = useMotionValue(0), py = useMotionValue(0);
  const sx = useSpring(px, { stiffness: 80, damping: 18, mass: 0.8 });
  const sy = useSpring(py, { stiffness: 80, damping: 18, mass: 0.8 });
  const rotateY = useTransform(sx, [-0.5, 0.5], [-3.5, 3.5]);
  const rotateX = useTransform(sy, [-0.5, 0.5], [2.8, -2.8]);

  useEffect(() => {
    api<Impact>(`/api/impact/notice?source_id=${encodeURIComponent(NOTICE)}`, { method: "POST" })
      .then((x) => (x.status === "ok" ? setR(x) : setError(true))).catch(() => setError(true));
  }, []);

  const g = useMemo(() => {
    if (!r) return null;
    const base = layout(r.graph.nodes, r.graph.edges, r.part.id);
    return { ...base, pos: relax(base.pos, base.level, base.maxLevel) };
  }, [r]);
  const labels = useMemo(() => (r && g ? placeLabels(r.graph.nodes, g.pos, g.level) : new Map<string, Label>()), [r, g]);
  const byId = useMemo(() => new Map(r?.graph.nodes.map((n) => [n.id, n]) ?? []), [r]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    r?.graph.nodes.forEach((n) => { c[n.type] = (c[n.type] ?? 0) + 1; });
    return c;
  }, [r]);
  // What each ring holds, for its caption.
  const rings = useMemo(() => {
    const out = new Map<number, Record<string, number>>();
    if (!r || !g) return out;
    for (const n of r.graph.nodes) {
      const l = g.level.get(n.id) ?? 0;
      if (!l) continue;
      const c = out.get(l) ?? {};
      c[n.type] = (c[n.type] ?? 0) + 1;
      out.set(l, c);
    }
    return out;
  }, [r, g]);

  // The record under the pointer (or the one clicked) lights up with its whole chain back to the changed part and
  // everything it leads to; hovering a ring lights that ring and the paths into it. The rest steps back.
  const active = hover ?? focus;
  const lit = useMemo(() => {
    if (!g) return null;
    const seeds = active ? [active] : ring !== null ? [...g.level].filter(([, l]) => l === ring).map(([id]) => id) : [];
    if (!seeds.length) return null;
    const out = new Set<string>(seeds);
    const up = [...seeds];
    while (up.length) for (const p of g.parents.get(up.pop()!) ?? []) if (!out.has(p)) { out.add(p); up.push(p); }
    if (active) {
      const down = [active];
      while (down.length) for (const c of g.children.get(down.pop()!) ?? []) if (!out.has(c)) { out.add(c); down.push(c); }
    }
    return out;
  }, [g, active, ring]);
  const excited = !!lit; // the orb answers whatever you point at

  const delay = (l: number) => (reduce ? 0 : 0.3 + l * STEP);
  const close = useCallback(() => setFocus(null), []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [close]);

  // Clicking a record glides the view towards it.
  const view = useMemo(() => {
    const p = focus && g?.pos.get(focus);
    if (!p) return `0 0 ${W} ${H}`;
    const z = 1.45, w = W / z, h = H / z;
    const x = Math.min(Math.max(p.x - w / 2, 0), W - w), y = Math.min(Math.max(p.y - h / 2, 0), H - h);
    return `${x.toFixed(1)} ${y.toFixed(1)} ${w.toFixed(1)} ${h.toFixed(1)}`;
  }, [focus, g]);

  const toScreen = (id: string) => {
    const p = g?.pos.get(id);
    if (!p) return null;
    const [vx, vy, vw, vh] = view.split(" ").map(Number);
    return { left: `${((p.x - vx) / vw) * 100}%`, top: `${((p.y - vy) / vh) * 100}%` };
  };

  if (error) return null;
  const hovered = hover ? byId.get(hover) : null;
  const focused = focus ? byId.get(focus) : null;
  const neighbours = focused && g ? [...(g.parents.get(focused.id) ?? []), ...(g.children.get(focused.id) ?? [])].map((id) => byId.get(id)).filter(Boolean) as GNode[] : [];
  const ringCaption = ring !== null && !active ? rings.get(ring) : null;

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
          <button onClick={() => { setFocus(null); setRing(null); setRun((x) => x + 1); }} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12.5px] text-muted hover:border-line2 hover:text-ink">
            <RotateCcw size={13} /> Replay</button>
          <Link href={`/impact?source=${encodeURIComponent(NOTICE)}`} className="press flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-[12.5px] font-medium text-accent-ink hover:bg-accent-hover">
            Open the impact <ArrowRight size={13} /></Link>
        </div>
      </div>

      <div ref={box} className="relative"
           onPointerMove={(e) => {
             const b = box.current?.getBoundingClientRect();
             if (!b) return;
             setSpot({ x: e.clientX - b.left, y: e.clientY - b.top });
             if (!reduce) { px.set((e.clientX - b.left) / b.width - 0.5); py.set((e.clientY - b.top) / b.height - 0.5); }
           }}
           onPointerLeave={() => { setSpot(null); setHover(null); setRing(null); px.set(0); py.set(0); }}>
        {/* A soft light that follows the pointer across the map. */}
        {spot && !reduce && (
          <div aria-hidden className="pointer-events-none absolute inset-0 transition-opacity duration-500"
               style={{ background: `radial-gradient(280px circle at ${spot.x}px ${spot.y}px, color-mix(in oklch, var(--accent) 8%, transparent), transparent 70%)` }} />
        )}
        {!g && <div className="m-5 skeleton h-[300px]" />}
        {g && r && (
          <motion.div style={{ rotateX, rotateY, transformPerspective: 1600 }} className="will-change-transform">
          <motion.svg key={run} viewBox={`0 0 ${W} ${H}`} animate={{ viewBox: view }} transition={{ duration: reduce ? 0 : 0.9, ease: EASE }}
                      className="relative block h-auto w-full touch-manipulation" role="img"
                      aria-label={`Impact of the ${r.part.id} change across ${r.graph.nodes.length} records`}
                      onClick={(e) => { if (e.target === e.currentTarget) setFocus(null); }}>
            <defs>
              <clipPath id="orb-clip"><circle r={24} /></clipPath>
              <filter id="orb-liquid" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4.5" /></filter>
              <filter id="orb-halo" x="-150%" y="-150%" width="400%" height="400%"><feGaussianBlur stdDeviation="16" /></filter>
              <filter id="orb-soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.6" /></filter>
              <radialGradient id="orb-sheen" cx="50%" cy="50%" r="50%">
                <stop offset="62%" stopColor="white" stopOpacity="0" />
                <stop offset="92%" stopColor="white" stopOpacity="0.14" />
                <stop offset="100%" stopColor="white" stopOpacity="0.32" />
              </radialGradient>
              <radialGradient id="dot-gloss" cx="35%" cy="30%" r="70%">
                <stop offset="0%" stopColor="white" stopOpacity="0.5" />
                <stop offset="60%" stopColor="white" stopOpacity="0.06" />
                <stop offset="100%" stopColor="white" stopOpacity="0" />
              </radialGradient>
            </defs>

            {/* Rings: hover one to light everything at that distance from the change. */}
            {Array.from({ length: g.maxLevel }).map((_, i) => {
              const l = i + 1, k = ringScale(l, g.maxLevel);
              const on = ring === l && !active;
              return (
                <g key={`ring${l}`}>
                  <motion.ellipse cx={CX} cy={CY} rx={k * (W / 2 - 80)} ry={k * (H / 2 - 40)} fill="none"
                                  style={{ stroke: on ? "var(--accent)" : "var(--line2)" }} strokeDasharray={on ? "0" : "1 7"} strokeLinecap="round"
                                  strokeWidth={on ? 1.2 : 1} className="ripple-dim"
                                  initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: lit && !on ? 0.35 : on ? 0.8 : 1, scale: 1 }}
                                  transition={{ delay: lit ? 0 : delay(l) - 0.2, duration: 0.8, ease: EASE }} />
                  <ellipse cx={CX} cy={CY} rx={k * (W / 2 - 80)} ry={k * (H / 2 - 40)} fill="none" stroke="transparent" strokeWidth={14}
                           style={{ pointerEvents: "stroke", cursor: "help" }} onMouseEnter={() => setRing(l)} onMouseLeave={() => setRing((x) => (x === l ? null : x))} />
                </g>
              );
            })}
            {!reduce && [0, 1, 2].map((i) => (
              <motion.ellipse key={`pulse${i}`} cx={CX} cy={CY} fill="none" style={{ stroke: "var(--accent)", pointerEvents: "none" }} strokeWidth={1}
                              initial={{ rx: 18, ry: 18, opacity: 0.32 }} animate={{ rx: W / 2 - 60, ry: H / 2 - 30, opacity: 0 }}
                              transition={{ duration: 6.6, delay: 1.2 + i * 2.2, repeat: Infinity, ease: [0.22, 0.61, 0.36, 1] }} />
            ))}

            {/* Connections: faint at rest, with light gliding outward; the lit chain carries a brighter flow. */}
            <g style={{ pointerEvents: "none" }}>
              {r.graph.edges.map((e, i) => {
                const a = g.pos.get(e.source), b = g.pos.get(e.target);
                if (!a || !b) return null;
                const out = (g.level.get(e.source) ?? 0) <= (g.level.get(e.target) ?? 0);
                const from = out ? a : b, to = out ? b : a;
                const l = Math.max(g.level.get(e.source) ?? 0, g.level.get(e.target) ?? 0);
                const on = lit ? lit.has(e.source) && lit.has(e.target) : false;
                const d = curve(from, to);
                const tint = colorOf(byId.get(out ? e.target : e.source)?.type ?? "");
                const dur = (3.6 + (i % 5) * 0.35).toFixed(2), begin = (delay(l) + 0.5 + (i % 9) * 0.45).toFixed(2);
                return (
                  <g key={i} className="ripple-dim" style={{ opacity: lit && !on ? 0.1 : 1 }}>
                    <motion.path d={d} fill="none" strokeLinecap="round" className="ripple-dim"
                                 style={{ stroke: on ? tint : "var(--line2)" }} strokeWidth={on ? 1.6 : 1}
                                 initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: 1 }}
                                 transition={{ delay: delay(l) - 0.3, duration: 0.7, ease: EASE }} />
                    {!reduce && on && (
                      <path d={d} fill="none" pathLength={100} className="ripple-flow-lit" strokeWidth={2.4} style={{ stroke: tint }} />
                    )}
                    {!reduce && (
                      <circle r={on ? 2.4 : 1.7} style={{ fill: on ? tint : "var(--accent)" }} opacity={0}>
                        <animateMotion dur={`${dur}s`} begin={`${begin}s`} repeatCount="indefinite" path={d}
                                       calcMode="spline" keyTimes="0;1" keyPoints="0;1" keySplines="0.45 0 0.25 1" />
                        <animate attributeName="opacity" values="0;0.9;0.9;0" keyTimes="0;0.15;0.75;1" dur={`${dur}s`} begin={`${begin}s`} repeatCount="indefinite" />
                      </circle>
                    )}
                  </g>
                );
              })}
            </g>

            {/* The orb: the changed part, as liquid light. Soft colours swirl inside a glass sphere and blend; the halo
                is the same light, blurred. It swells and brightens whenever you point at something. */}
            <g transform={`translate(${CX} ${CY})`} style={{ pointerEvents: "none" }}>
              <motion.g initial={{ opacity: 0, scale: 0.5 }} animate={{ opacity: excited ? 1 : 0.72, scale: excited ? 1.25 : 1 }}
                        transition={{ type: "spring", stiffness: 90, damping: 18, delay: excited ? 0 : delay(0) }}>
                <g filter="url(#orb-halo)">
                  <OrbLight reduce={!!reduce} spread={1.75} />
                </g>
              </motion.g>
              <motion.g initial={{ opacity: 0, scale: 0.3 }} animate={{ opacity: 1, scale: excited ? 1.12 : 1 }}
                        transition={{ type: "spring", stiffness: 180, damping: 17, delay: excited ? 0 : delay(0) }}>
                <circle r={24} style={{ fill: "color-mix(in oklch, var(--panel) 60%, #1d2a6b)" }} />
                <g clipPath="url(#orb-clip)">
                  <g filter="url(#orb-liquid)"><OrbLight reduce={!!reduce} spread={1.15} /></g>
                  {/* the light inside, so it glows from within rather than looking painted */}
                  <motion.circle r={9} fill="white" filter="url(#orb-liquid)" animate={reduce ? undefined : { opacity: [0.22, 0.4, 0.22] }}
                                 transition={{ duration: 3.6, repeat: Infinity, ease: "easeInOut" }} opacity={0.3} />
                </g>
                <circle r={24} fill="url(#orb-sheen)" />
                <circle r={23.6} fill="none" stroke="white" strokeOpacity={0.5} strokeWidth={0.7} />
                <ellipse cx={-7} cy={-10.5} rx={8} ry={4.4} fill="white" opacity={0.38} transform="rotate(-28 -7 -10.5)" filter="url(#orb-soft)" />
              </motion.g>
            </g>

            {/* Records */}
            {r.graph.nodes.map((n) => {
              const p = g.pos.get(n.id);
              if (!p) return null;
              const l = g.level.get(n.id) ?? 0;
              if (l === 0) return (
                <g key={n.id} transform={`translate(${p.x} ${p.y})`} role="button" tabIndex={0} aria-label={`${n.label}, ${KIND[n.type]?.label ?? n.type}`}
                   style={{ cursor: "pointer" }} onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
                   onClick={(ev) => { ev.stopPropagation(); setFocus((f) => (f === n.id ? null : n.id)); }}>
                  <circle r={30} fill="transparent" />
                </g>
              );
              const isOn = !lit || lit.has(n.id);
              const isActive = active === n.id;
              return (
                <g key={n.id} transform={`translate(${p.x} ${p.y})`} className="ripple-dim" style={{ opacity: isOn ? 1 : 0.2 }}>
                  <g className={reduce ? "" : "ripple-drift"} style={{ animationDelay: `${((n.id.length * 37) % 70) / 10}s` }}>
                    <motion.g style={{ cursor: "pointer" }} role="button" tabIndex={0} aria-label={`${n.label}, ${KIND[n.type]?.label ?? n.type}`}
                              onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
                              onFocus={() => setHover(n.id)} onBlur={() => setHover(null)}
                              onClick={(ev) => { ev.stopPropagation(); setFocus((f) => (f === n.id ? null : n.id)); }}
                              onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); setFocus(n.id); } }}
                              initial={{ opacity: 0, scale: 0.2 }} animate={{ opacity: 1, scale: isActive ? 1.4 : 1 }}
                              whileHover={{ scale: 1.4 }} whileTap={{ scale: 0.92 }}
                              transition={{ opacity: { delay: delay(l), duration: 0.45 }, scale: isActive || lit ? { type: "spring", stiffness: 380, damping: 22 } : { delay: delay(l), type: "spring", stiffness: 260, damping: 17 } }}>
                      <circle r={16} fill="transparent" />
                      <circle r={isActive || (lit && isOn) ? 12 : 10} style={{ fill: colorOf(n.type), opacity: isActive ? 0.28 : 0.12 }} className="ripple-dim" />
                      <circle r={6} style={{ fill: colorOf(n.type), stroke: "var(--panel)" }} strokeWidth={1.5} />
                      <circle r={6} fill="url(#dot-gloss)" />
                      {isActive && (
                        <motion.circle r={10} fill="none" style={{ stroke: colorOf(n.type) }} strokeWidth={1}
                                       initial={{ opacity: 0.8, scale: 1 }} animate={{ opacity: 0, scale: 2 }} transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }} />
                      )}
                    </motion.g>
                  </g>
                </g>
              );
            })}

            {/* Names, placed so they never overlap; any that cannot fit appear when their record is lit. */}
            <g style={{ pointerEvents: "none" }} className="select-none font-mono">
              {r.graph.nodes.map((n) => {
                const p = g.pos.get(n.id);
                if (!p) return null;
                const l = g.level.get(n.id) ?? 0;
                if (l === 0) return (
                  <motion.text key={n.id} x={CX} y={CY + 56} textAnchor="middle" initial={{ opacity: 0, filter: "blur(4px)" }} animate={{ opacity: 1, filter: "blur(0px)" }}
                               transition={{ delay: delay(0) + 0.2, duration: 0.6, ease: EASE }}
                               style={{ fill: "var(--ink)", fontSize: 15, fontWeight: 600, letterSpacing: "0.04em", paintOrder: "stroke", stroke: "var(--panel)", strokeWidth: 4 }}>
                    {n.label}
                  </motion.text>
                );
                const lab = labels.get(n.id);
                if (!lab) return null;
                const isActive = active === n.id;
                const isOn = !lit || lit.has(n.id);
                const show = lab.fits ? (isOn ? 1 : 0.18) : (lit && lit.has(n.id) ? 1 : 0);
                return (
                  <motion.text key={n.id} x={lab.x} y={lab.y} textAnchor={lab.anchor} className="ripple-dim ripple-label"
                               initial={{ opacity: 0, filter: "blur(3px)" }} animate={{ opacity: show, filter: "blur(0px)" }}
                               transition={{ opacity: { delay: lit ? 0 : delay(l) + 0.15, duration: 0.45, ease: EASE }, filter: { delay: delay(l) + 0.15, duration: 0.5 } }}
                               style={{ fill: isActive || (lit && isOn) ? "var(--ink)" : "var(--muted)", fontSize: 10.5, fontWeight: isActive ? 600 : 400,
                                        paintOrder: "stroke", stroke: "var(--panel)", strokeWidth: 3 }}>
                    {isActive ? n.label : short(n.label)}
                  </motion.text>
                );
              })}
            </g>
          </motion.svg>
          </motion.div>
        )}

        <AnimatePresence>
          {ringCaption && ring !== null && (
            <motion.div key={`ring${ring}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }} transition={{ duration: 0.25, ease: EASE }}
                        className="surface-pop pointer-events-none absolute left-4 top-3 z-10 px-3 py-2 text-[12.5px]">
              <div className="font-medium">{ring === 1 ? "One step from the change" : `${ring} steps from the change`}</div>
              <div className="text-muted">{Object.entries(ringCaption).map(([t, c]) => `${c} ${c === 1 ? KIND[t]?.label ?? t : PLURAL[t] ?? `${KIND[t]?.label ?? t}s`}`).join(" · ")}</div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {hovered && hover !== focus && (() => {
            const at = toScreen(hovered.id);
            return at && (
              <motion.div key={hovered.id} initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 4, scale: 0.98 }}
                          transition={{ duration: 0.22, ease: EASE }}
                          className="surface-pop pointer-events-none absolute z-10 max-w-[260px] -translate-x-1/2 px-3 py-2 text-[12.5px]"
                          style={{ left: at.left, top: `calc(${at.top} - 74px)` }}>
                <div className="flex items-center gap-1.5 font-medium"><span className="h-2 w-2 rounded-full" style={{ background: colorOf(hovered.type) }} />{hovered.label}</div>
                <div className="text-muted">{KIND[hovered.type]?.label ?? hovered.type}{hovered.name && hovered.name !== hovered.label ? ` · ${hovered.name}` : ""}</div>
              </motion.div>
            );
          })()}
        </AnimatePresence>

        <AnimatePresence>
          {focused && (
            <motion.div key={focused.id} initial={{ opacity: 0, y: 12, filter: "blur(6px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                        exit={{ opacity: 0, y: 8, filter: "blur(4px)" }} transition={{ duration: 0.4, ease: EASE }}
                        className="surface-pop absolute bottom-4 left-4 z-10 w-[min(320px,calc(100%-2rem))] p-4">
              <div className="flex items-start gap-2.5">
                <span className="mt-1 h-3 w-3 shrink-0 rounded-full" style={{ background: colorOf(focused.type), boxShadow: `0 0 12px ${colorOf(focused.type)}` }} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-[14px] font-semibold">{focused.label}</div>
                  <div className="text-[12px] text-muted">{KIND[focused.type]?.label ?? focused.type}{focused.name && focused.name !== focused.label ? ` · ${focused.name}` : ""}{focused.role ? ` · ${focused.role}` : ""}</div>
                </div>
                <button onClick={close} aria-label="Close" className="rounded-md p-1 text-faint hover:bg-elev hover:text-ink"><X size={14} /></button>
              </div>
              {neighbours.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {neighbours.slice(0, 8).map((x) => (
                    <button key={x.id} onClick={() => setFocus(x.id)} onMouseEnter={() => setHover(x.id)} onMouseLeave={() => setHover(null)}
                            className="flex items-center gap-1 rounded-full border border-line bg-panel px-2 py-0.5 font-mono text-[11px] text-ink-soft hover:border-line2 hover:text-ink">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: colorOf(x.type) }} />{x.label}
                    </button>
                  ))}
                </div>
              )}
              <button onClick={() => router.push(`/explore?id=${encodeURIComponent(focused.id)}`)}
                      className="press mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl bg-accent px-3 py-1.5 text-[12.5px] font-medium text-accent-ink hover:bg-accent-hover">
                Explore {focused.label} <ArrowUpRight size={13} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {r && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-line px-5 py-3 text-[12px] text-muted">
          {Object.keys(LEGEND).filter((t) => counts[t]).map((t, i) => (
            <motion.span key={t} className="flex items-center gap-1.5" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: delay(i), duration: 0.4, ease: EASE }}>
              <span className="h-2 w-2 rounded-full" style={{ background: colorOf(t), boxShadow: `0 0 8px ${colorOf(t)}` }} />
              <span className="num font-semibold text-ink">{counts[t]}</span> {LEGEND[t]}
            </motion.span>
          ))}
          <span className="ml-auto text-faint">Hover a record or a ring · click to focus</span>
        </div>
      )}
    </section>
  );
}
