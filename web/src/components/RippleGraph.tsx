"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, ArrowUpRight, RotateCcw, Waves, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";

type GNode = { id: string; type: string; label: string; name?: string; role?: string };
type GEdge = { source: string; target: string; label: string };
type Impact = { status: string; part: { id: string; name: string }; graph: { nodes: GNode[]; edges: GEdge[] } };

const NOTICE = "inbox/notice_NB54360_2026-10-14.md";
const W = 1000, H = 580, CX = W / 2, CY = H / 2;
// Ring spacing: inner rings get more room than a linear spacing would give them, so labels near the centre breathe.
const ringScale = (l: number, max: number) => 0.24 + 0.76 * Math.pow(l / max, 0.85);
const STEP = 0.5; // seconds between rings
const EASE = [0.16, 1, 0.3, 1] as const;

// What each kind of record is, in the order a change travels.
const KIND: Record<string, { label: string; color: string }> = {
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
const LEGEND: Record<string, string> = { part: "changed part", revision: "product revisions", build: "builds", order: "customer orders",
  customer: "customers", person: "people", decision: "past decisions" };
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

export default function RippleGraph() {
  const router = useRouter();
  const reduce = useReducedMotion();
  const [r, setR] = useState<Impact | null>(null);
  const [error, setError] = useState(false);
  const [run, setRun] = useState(0);
  const [hover, setHover] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [spot, setSpot] = useState<{ x: number; y: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<Impact>(`/api/impact/notice?source_id=${encodeURIComponent(NOTICE)}`, { method: "POST" })
      .then((x) => (x.status === "ok" ? setR(x) : setError(true))).catch(() => setError(true));
  }, []);

  const g = useMemo(() => (r ? layout(r.graph.nodes, r.graph.edges, r.part.id) : null), [r]);
  const byId = useMemo(() => new Map(r?.graph.nodes.map((n) => [n.id, n]) ?? []), [r]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    r?.graph.nodes.forEach((n) => { c[n.type] = (c[n.type] ?? 0) + 1; });
    return c;
  }, [r]);

  // The record under the pointer (or the one clicked) lights up with its whole chain back to the changed part,
  // and everything it leads to; the rest of the company steps back.
  const active = hover ?? focus;
  const lit = useMemo(() => {
    if (!g || !active) return null;
    const out = new Set<string>([active]);
    const up = [active];
    while (up.length) for (const p of g.parents.get(up.pop()!) ?? []) if (!out.has(p)) { out.add(p); up.push(p); }
    const down = [active];
    while (down.length) for (const c of g.children.get(down.pop()!) ?? []) if (!out.has(c)) { out.add(c); down.push(c); }
    return out;
  }, [g, active]);

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
          <button onClick={() => { setFocus(null); setRun((x) => x + 1); }} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12.5px] text-muted hover:border-line2 hover:text-ink">
            <RotateCcw size={13} /> Replay</button>
          <Link href={`/impact?source=${encodeURIComponent(NOTICE)}`} className="press flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-[12.5px] font-medium text-accent-ink hover:bg-accent-hover">
            Open the impact <ArrowRight size={13} /></Link>
        </div>
      </div>

      <div ref={box} className="relative"
           onPointerMove={(e) => { const b = box.current?.getBoundingClientRect(); if (b) setSpot({ x: e.clientX - b.left, y: e.clientY - b.top }); }}
           onPointerLeave={() => { setSpot(null); setHover(null); }}>
        {/* A soft light that follows the pointer across the map. */}
        {spot && !reduce && (
          <div aria-hidden className="pointer-events-none absolute inset-0 transition-opacity duration-500"
               style={{ background: `radial-gradient(260px circle at ${spot.x}px ${spot.y}px, color-mix(in oklch, var(--accent) 9%, transparent), transparent 70%)` }} />
        )}
        {!g && <div className="m-5 skeleton h-[300px]" />}
        {g && r && (
          <motion.svg key={run} viewBox={`0 0 ${W} ${H}`} animate={{ viewBox: view }} transition={{ duration: reduce ? 0 : 0.9, ease: EASE }}
                      className="relative block h-auto w-full touch-manipulation" role="img"
                      aria-label={`Impact of the ${r.part.id} change across ${r.graph.nodes.length} records`}
                      onClick={(e) => { if (e.target === e.currentTarget) setFocus(null); }}>
            <defs>
              <radialGradient id="ripple-gloss" cx="35%" cy="30%" r="70%">
                <stop offset="0%" stopColor="white" stopOpacity="0.55" />
                <stop offset="55%" stopColor="white" stopOpacity="0.08" />
                <stop offset="100%" stopColor="white" stopOpacity="0" />
              </radialGradient>
              <radialGradient id="ripple-core" cx="50%" cy="50%" r="50%">
                <stop offset="0%" style={{ stopColor: "var(--accent)" }} stopOpacity="0.32" />
                <stop offset="100%" style={{ stopColor: "var(--accent)" }} stopOpacity="0" />
              </radialGradient>
              <filter id="ripple-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="5" />
              </filter>
            </defs>

            <circle cx={CX} cy={CY} r={120} fill="url(#ripple-core)" />
            {Array.from({ length: g.maxLevel }).map((_, i) => (
              <motion.ellipse key={`ring${i}`} cx={CX} cy={CY} rx={ringScale(i + 1, g.maxLevel) * (W / 2 - 80)} ry={ringScale(i + 1, g.maxLevel) * (H / 2 - 40)}
                              fill="none" style={{ stroke: "var(--line)" }} strokeDasharray="1 7" strokeLinecap="round"
                              initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: lit ? 0.4 : 1, scale: 1 }}
                              transition={{ delay: lit ? 0 : delay(i + 1) - 0.2, duration: 0.8, ease: EASE }} />
            ))}
            {!reduce && [0, 1].map((i) => (
              <motion.ellipse key={`pulse${i}`} cx={CX} cy={CY} fill="none" style={{ stroke: "var(--accent)" }} strokeWidth={1}
                              initial={{ rx: 10, ry: 10, opacity: 0.35 }} animate={{ rx: W / 2 - 60, ry: H / 2 - 30, opacity: 0 }}
                              transition={{ duration: 5.5, delay: 1.2 + i * 2.75, repeat: Infinity, ease: [0.22, 0.61, 0.36, 1] }} />
            ))}

            {r.graph.edges.map((e, i) => {
              const a = g.pos.get(e.source), b = g.pos.get(e.target);
              if (!a || !b) return null;
              // Always draw from the record nearer the change to the one further out.
              const out = (g.level.get(e.source) ?? 0) <= (g.level.get(e.target) ?? 0);
              const from = out ? a : b, to = out ? b : a;
              const l = Math.max(g.level.get(e.source) ?? 0, g.level.get(e.target) ?? 0);
              const on = lit ? lit.has(e.source) && lit.has(e.target) : false;
              const d = curve(from, to);
              const tint = colorOf(byId.get(out ? e.target : e.source)?.type ?? "");
              return (
                <g key={i} className="ripple-dim" style={{ opacity: lit && !on ? 0.12 : 1 }}>
                  <motion.path d={d} fill="none" strokeLinecap="round" className="ripple-dim"
                               style={{ stroke: on ? tint : "var(--line2)" }} strokeWidth={on ? 1.8 : 1}
                               initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: 1 }}
                               transition={{ delay: delay(l) - 0.3, duration: 0.7, ease: EASE }} />
                  {!reduce && (
                    <path d={d} fill="none" pathLength={100} className="ripple-flow" strokeWidth={on ? 2.6 : 1.6}
                          style={{ stroke: on ? tint : "var(--accent)", opacity: on ? 0.95 : 0.35, animationDelay: `${(delay(l) + (i % 7) * 0.6).toFixed(2)}s` }} />
                  )}
                </g>
              );
            })}

            {r.graph.nodes.map((n) => {
              const p = g.pos.get(n.id);
              if (!p) return null;
              const l = g.level.get(n.id) ?? 0;
              const center = l === 0;
              const isOn = !lit || lit.has(n.id);
              const isActive = active === n.id;
              const rad = center ? 15 : 7;
              return (
                <g key={n.id} transform={`translate(${p.x} ${p.y})`} className="ripple-dim" style={{ opacity: isOn ? 1 : 0.22 }}>
                  <g className={reduce ? "" : "ripple-drift"} style={{ animationDelay: `${((n.id.length * 37) % 70) / 10}s` }}>
                    <motion.g style={{ cursor: "pointer" }} role="button" tabIndex={0} aria-label={`${n.label}, ${KIND[n.type]?.label ?? n.type}`}
                              onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
                              onFocus={() => setHover(n.id)} onBlur={() => setHover(null)}
                              onClick={(ev) => { ev.stopPropagation(); setFocus((f) => (f === n.id ? null : n.id)); }}
                              onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); setFocus(n.id); } }}
                              initial={{ opacity: 0, scale: 0.2 }} animate={{ opacity: 1, scale: isActive ? 1.35 : 1 }}
                              whileHover={{ scale: center ? 1.08 : 1.35 }} whileTap={{ scale: 0.92 }}
                              transition={{ opacity: { delay: delay(l), duration: 0.4 }, scale: isActive || lit ? { type: "spring", stiffness: 380, damping: 22 } : { delay: delay(l), type: "spring", stiffness: 260, damping: 17 } }}>
                      <circle r={rad + 10} fill="transparent" />
                      {(center || isActive) && <circle r={rad + 9} style={{ fill: colorOf(n.type), opacity: 0.22 }} filter="url(#ripple-glow)" />}
                      {center && <circle r={26} style={{ fill: "var(--accent)", opacity: 0.14 }} />}
                      <circle r={rad} style={{ fill: colorOf(n.type), stroke: "var(--panel)" }} strokeWidth={2} />
                      <circle r={rad} fill="url(#ripple-gloss)" />
                      {isActive && !center && (
                        <motion.circle r={rad + 4} fill="none" style={{ stroke: colorOf(n.type) }} strokeWidth={1}
                                       initial={{ opacity: 0.8, scale: 1 }} animate={{ opacity: 0, scale: 1.9 }} transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }} />
                      )}
                    </motion.g>
                    {/* The label arrives with its record, ring by ring. */}
                    <motion.text y={center ? 34 : 20} textAnchor="middle" className="pointer-events-none select-none font-mono ripple-dim"
                                 initial={{ opacity: 0, y: center ? 38 : 24 }} animate={{ opacity: 1, y: center ? 34 : 20 }}
                                 transition={{ delay: delay(l) + 0.12, duration: 0.45, ease: EASE }}
                                 style={{ fill: center || isActive ? "var(--ink)" : "var(--muted)", fontSize: center ? 15 : 10.5, fontWeight: isActive ? 600 : 400,
                                          paintOrder: "stroke", stroke: "var(--panel)", strokeWidth: 3 }}>
                      {n.label.length > 16 && !isActive ? n.label.slice(0, 15) + "…" : n.label}
                    </motion.text>
                  </g>
                </g>
              );
            })}
          </motion.svg>
        )}

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
          <span className="ml-auto text-faint">Hover to trace a path · click to focus</span>
        </div>
      )}
    </section>
  );
}
