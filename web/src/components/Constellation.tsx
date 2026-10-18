"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, ArrowUpRight, RotateCcw, Waves, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import RippleGraph, { KIND, LEGEND, NOTICE, layout, type GNode, type Impact } from "@/components/RippleGraph";
import { api } from "@/lib/api";

// One colour per kind of record, tuned to glow on the dark sky.
const HEX: Record<string, string> = {
  part: "#7aa2ff", revision: "#22d3ee", build: "#fbbf24", order: "#a78bfa", customer: "#fb7185", person: "#e2e8f0",
  decision: "#f87171", alternate: "#94a3b8", shipment: "#f59e0b", firmware: "#34d399", test: "#34d399",
};
const hex = (t: string) => HEX[t] ?? "#94a3b8";
const SKY = "#04060c";
const EASE = [0.16, 1, 0.3, 1] as const;
const STEP = 0.45; // seconds between rings as the change spreads

const hash = (s: string) => { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return ((h >>> 0) % 10000) / 10000; };
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const backOut = (x: number) => { const c = 1.70158; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };

function webgl(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch { return false; }
}

function glowTexture(inner = 0.0, outer = 0.5) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(64, 64, 64 * inner, 64, 64, 64 * outer * 2);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.25, "rgba(255,255,255,0.55)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

type NodeObj = { id: string; level: number; pos: THREE.Vector3; mesh: THREE.Mesh; halo: THREE.Sprite; hit: THREE.Mesh;
                 label: CSS2DObject; r: number; dim: number };
type EdgeObj = { a: string; b: string; level: number; line: Line2; geo: LineGeometry; segments: number; curve: THREE.QuadraticBezierCurve3 };

/** The overview's hero: one supplier change spreading through the company, as a living 3D constellation. */
export default function Constellation() {
  const [gl, setGl] = useState<boolean | null>(null);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGl(webgl()));
    return () => cancelAnimationFrame(id);
  }, []);
  if (gl === false) return <RippleGraph />;
  return <Scene />;
}

function Scene() {
  const router = useRouter();
  const reduce = useReducedMotion();
  const [r, setR] = useState<Impact | null>(null);
  const [error, setError] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const mount = useRef<HTMLDivElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const startRef = useRef(0);
  const hoverRef = useRef<string | null>(null);
  const focusRef = useRef<string | null>(null);
  const reduceRef = useRef(false);
  const litRef = useRef<Set<string> | null>(null);

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

  useEffect(() => { reduceRef.current = !!reduce; }, [reduce]);
  useEffect(() => { focusRef.current = focus; }, [focus]);

  // ---------- the scene ----------
  useEffect(() => {
    const host = mount.current;
    if (!host || !r || !g) return;
    const reduceNow = reduceRef.current;
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(SKY, 0.016);
    const camera = new THREE.PerspectiveCamera(42, 2, 0.1, 400);
    const renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: "high-performance" });
    // Quality adapts to the machine: full bloom where the GPU keeps up, a lighter sky where it does not.
    const quality = { ratio: Math.min(window.devicePixelRatio, 1.5), bloom: true };
    renderer.setPixelRatio(quality.ratio);
    renderer.setClearColor(SKY, 1);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    host.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";
    renderer.domElement.setAttribute("aria-hidden", "true");

    const labels = new CSS2DRenderer();
    labels.domElement.style.position = "absolute";
    labels.domElement.style.inset = "0";
    labels.domElement.style.pointerEvents = "none";
    host.appendChild(labels.domElement);

    const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 }));
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), 0.62, 0.42, 0.22);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.enableZoom = false;
    controls.enablePan = false;
    controls.rotateSpeed = 0.55;
    controls.minPolarAngle = 0.35;
    controls.maxPolarAngle = 1.35;
    controls.autoRotate = !reduceNow;
    controls.autoRotateSpeed = 0.55;
    if (window.matchMedia("(pointer: coarse)").matches) {
      controls.enabled = false; // let the page scroll on touch screens; the sky still turns by itself
      renderer.domElement.style.touchAction = "pan-y";
    }

    const glow = glowTexture();
    const world = new THREE.Group();
    scene.add(world);

    // Stars and a polar grid give the sky depth.
    const starGeo = new THREE.BufferGeometry();
    const starPos = new Float32Array(1600 * 3);
    for (let i = 0; i < 1600; i++) {
      const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, rad = 45 + Math.random() * 60;
      starPos.set([rad * Math.sqrt(1 - u * u) * Math.cos(th), rad * u, rad * Math.sqrt(1 - u * u) * Math.sin(th)], i * 3);
    }
    starGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
    const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ color: "#9fb4ff", size: 0.16, sizeAttenuation: true,
      transparent: true, opacity: 0.75, depthWrite: false, fog: false }));
    scene.add(stars);
    const grid = new THREE.PolarGridHelper(19, 16, 10, 96, "#2b3a66", "#16203d");
    grid.position.y = -2.6;
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.32;
    world.add(grid);

    // Records sit on rings by distance from the change, with a little height so the structure reads in depth.
    const maxLevel = g.maxLevel;
    // Inner rings hold most records, so they get more room than an even spacing would give them.
    const radius = (l: number) => (l === 0 ? 0 : 3.6 + 12.5 * Math.pow((l - 1) / Math.max(maxLevel - 1, 1), 0.72));
    const nodes = new Map<string, NodeObj>();
    for (const n of r.graph.nodes) {
      const p2 = g.pos.get(n.id);
      if (!p2) continue;
      const level = g.level.get(n.id) ?? 0;
      const a = Math.atan2((p2.y - 290) / 250, (p2.x - 500) / 420);
      const R = radius(level);
      const pos = level === 0 ? new THREE.Vector3(0, 0, 0)
        : new THREE.Vector3(R * Math.cos(a), (hash(n.id) - 0.5) * 2.2, R * Math.sin(a));
      const rr = level === 0 ? 0.55 : 0.2;
      const color = new THREE.Color(hex(n.type));
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(rr, 32, 32),
        new THREE.MeshBasicMaterial({ color: color.clone().multiplyScalar(level === 0 ? 1.15 : 0.95), transparent: true }));
      mesh.position.copy(pos);
      const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glow, color, transparent: true, opacity: level === 0 ? 0.55 : 0.32,
        blending: THREE.AdditiveBlending, depthWrite: false }));
      halo.scale.setScalar(rr * (level === 0 ? 5.5 : 5));
      halo.position.copy(pos);
      const hitMat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false });
      hitMat.colorWrite = false;
      const hit = new THREE.Mesh(new THREE.SphereGeometry(rr * 2.6, 12, 12), hitMat);
      hit.position.copy(pos);
      hit.userData.id = n.id;
      const el = document.createElement("div");
      el.className = `constellation-label${level === 0 ? " is-center" : ""}`;
      el.textContent = n.label.length > 18 ? n.label.slice(0, 17) + "…" : n.label;
      const label = new CSS2DObject(el);
      label.position.set(0, -(rr + (level === 0 ? 0.75 : 0.42)), 0);
      mesh.add(label);
      world.add(halo, mesh, hit);
      nodes.set(n.id, { id: n.id, level, pos, mesh, halo, hit, label, r: rr, dim: 1 });
    }

    // The core: the changed part, wrapped in a slowly turning lattice.
    const core = new THREE.LineSegments(new THREE.WireframeGeometry(new THREE.IcosahedronGeometry(1.1, 1)),
      new THREE.LineBasicMaterial({ color: "#8fb0ff", transparent: true, opacity: 0.32, blending: THREE.AdditiveBlending }));
    world.add(core);
    const orbitRings: THREE.LineLoop[] = [];
    for (let l = 1; l <= maxLevel; l++) {
      const pts = Array.from({ length: 160 }, (_, i) => {
        const t = (i / 160) * Math.PI * 2;
        return new THREE.Vector3(radius(l) * Math.cos(t), -0.2, radius(l) * Math.sin(t));
      });
      const ring = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineBasicMaterial({ color: "#3b5bb5", transparent: true, opacity: 0.0, depthWrite: false }));
      ring.userData.level = l;
      world.add(ring);
      orbitRings.push(ring);
    }

    // Connections: glowing beams from the record nearer the change to the one further out.
    const edges: EdgeObj[] = [];
    const lineMats: LineMaterial[] = [];
    for (const e of r.graph.edges) {
      const A = nodes.get(e.source), B = nodes.get(e.target);
      if (!A || !B) continue;
      const [from, to] = A.level <= B.level ? [A, B] : [B, A];
      const mid = from.pos.clone().add(to.pos).multiplyScalar(0.5);
      const outward = mid.clone().setY(0).normalize().multiplyScalar(Math.min(1.6, from.pos.distanceTo(to.pos) * 0.18));
      mid.add(outward).add(new THREE.Vector3(0, 0.55, 0));
      const curve = new THREE.QuadraticBezierCurve3(from.pos.clone(), mid, to.pos.clone());
      const pts = curve.getPoints(40);
      const geo = new LineGeometry();
      geo.setPositions(pts.flatMap((p) => [p.x, p.y, p.z]));
      const c1 = new THREE.Color(hex(byId.get(from.id)?.type ?? "")), c2 = new THREE.Color(hex(byId.get(to.id)?.type ?? ""));
      geo.setColors(pts.flatMap((_, i) => { const c = c1.clone().lerp(c2, i / 40); return [c.r, c.g, c.b]; }));
      const mat = new LineMaterial({ linewidth: 1.4, vertexColors: true, transparent: true, opacity: 0.42,
        blending: THREE.AdditiveBlending, depthWrite: false, worldUnits: false });
      lineMats.push(mat);
      const line = new Line2(geo, mat);
      line.computeLineDistances();
      geo.instanceCount = 0;
      world.add(line);
      edges.push({ a: from.id, b: to.id, level: to.level, line, geo, segments: 40, curve });
    }

    // Energy flowing outward along every connection.
    const perEdge = 2;
    const pulseGeo = new THREE.BufferGeometry();
    const pulsePos = new Float32Array(edges.length * perEdge * 3);
    const pulseCol = new Float32Array(edges.length * perEdge * 3);
    edges.forEach((e, i) => {
      const c = new THREE.Color(hex(byId.get(e.b)?.type ?? "")).multiplyScalar(1.1);
      for (let k = 0; k < perEdge; k++) pulseCol.set([c.r, c.g, c.b], (i * perEdge + k) * 3);
    });
    pulseGeo.setAttribute("position", new THREE.BufferAttribute(pulsePos, 3));
    pulseGeo.setAttribute("color", new THREE.BufferAttribute(pulseCol, 3));
    const pulses = new THREE.Points(pulseGeo, new THREE.PointsMaterial({ size: 0.32, map: glow, vertexColors: true, transparent: true,
      blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true }));
    pulses.visible = !reduceNow;
    world.add(pulses);

    // Shockwaves leave the changed part every few seconds.
    const waves = [0, 1, 2].map(() => {
      const m = new THREE.Mesh(new THREE.RingGeometry(0.996, 1, 160), new THREE.MeshBasicMaterial({ color: "#7aa2ff",
        transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
      m.rotation.x = -Math.PI / 2;
      m.position.y = -0.2;
      world.add(m);
      return m;
    });

    startRef.current = performance.now();

    // ---------- size, visibility, pointer ----------
    let width = 1, height = 1;
    const resize = () => {
      width = host.clientWidth;
      height = width < 640 ? Math.round(Math.min(560, width * 1.25)) : Math.round(Math.min(640, Math.max(380, width * 0.56)));
      host.style.height = `${height}px`;
      renderer.setSize(width, height);
      composer.setPixelRatio(quality.ratio);
      composer.setSize(width, height);
      bloom.resolution.set(Math.round(width / 2), Math.round(height / 2)); // the glow is soft; half resolution is plenty
      labels.setSize(width, height);
      lineMats.forEach((m) => m.resolution.set(width, height));
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    const baseDist = () => 26 * Math.max(1, (width < 640 ? 1.4 : 1.6) / camera.aspect);
    resize();
    camera.position.set(0, baseDist() * 0.42, baseDist());
    controls.update();
    const ro = new ResizeObserver(resize);
    ro.observe(host);
    let visible = true;
    const io = new IntersectionObserver(([en]) => { visible = en.isIntersecting; }, { threshold: 0.01 });
    io.observe(host);

    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const hits = [...nodes.values()].map((n) => n.hit);
    const pick = (ev: PointerEvent) => {
      const b = renderer.domElement.getBoundingClientRect();
      ndc.set(((ev.clientX - b.left) / b.width) * 2 - 1, -((ev.clientY - b.top) / b.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const found = ray.intersectObjects(hits, false)[0];
      return (found?.object.userData.id as string | undefined) ?? null;
    };
    const onMove = (ev: PointerEvent) => {
      const id = pick(ev);
      if (id !== hoverRef.current) { hoverRef.current = id; setHover(id); }
      renderer.domElement.style.cursor = id ? "pointer" : "grab";
    };
    let down: { x: number; y: number } | null = null;
    const onDown = (ev: PointerEvent) => { down = { x: ev.clientX, y: ev.clientY }; };
    const onUp = (ev: PointerEvent) => {
      if (!down || Math.hypot(ev.clientX - down.x, ev.clientY - down.y) > 6) { down = null; return; }
      down = null;
      const id = pick(ev);
      setFocus((f) => (id ? (f === id ? null : id) : null));
    };
    const onLeave = () => { hoverRef.current = null; setHover(null); };
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointerleave", onLeave);

    // ---------- the loop ----------
    let frame = 0;
    let frames = 0, windowStart = performance.now(), slow = 0;
    const govern = (now: number) => {
      frames++;
      if (now - windowStart < 1500) return;
      const fps = (frames * 1000) / (now - windowStart);
      frames = 0;
      windowStart = now;
      if (fps >= 28) { slow = 0; return; }
      if (++slow < 2) return; // two slow windows in a row before stepping down
      slow = 0;
      if (quality.bloom) quality.bloom = false;
      else if (quality.ratio > 1) { quality.ratio = 1; renderer.setPixelRatio(1); resize(); }
    };
    const target = new THREE.Vector3();
    const tmp = new THREE.Vector3();
    const loop = () => {
      frame = requestAnimationFrame(loop);
      if (!visible || document.hidden) { windowStart = performance.now(); frames = 0; return; }
      govern(performance.now());
      const reduceLive = reduceRef.current;
      const t = (performance.now() - startRef.current) / 1000;
      const appear = (l: number) => (reduceLive ? 1 : clamp01((t - (0.25 + l * STEP)) / 0.65));

      const litNow = litRef.current;
      for (const n of nodes.values()) {
        n.dim = !litNow || litNow.has(n.id) ? 1 : 0.14;
        const k = appear(n.level);
        const s = Math.max(0.0001, backOut(k));
        const breathe = n.level === 0 ? 1 + Math.sin(t * 2.2) * 0.06 : 1 + Math.sin(t * 1.3 + hash(n.id) * 6) * 0.04;
        const hovered = hoverRef.current === n.id || focusRef.current === n.id;
        n.mesh.scale.setScalar(s * (hovered ? 1.6 : 1));
        n.halo.scale.setScalar(n.r * (n.level === 0 ? 5.5 : 5) * s * breathe * (hovered ? 1.7 : 1));
        (n.mesh.material as THREE.MeshBasicMaterial).opacity = k * n.dim;
        // Without bloom (slow machines) the halos carry the glow on their own.
        const haloBoost = quality.bloom ? 1 : 1.8;
        (n.halo.material as THREE.SpriteMaterial).opacity = Math.min(1, k * n.dim * haloBoost * (n.level === 0 ? 0.55 : hovered ? 0.6 : 0.32));
        // Labels fade with distance, so the near side of the sky reads first.
        n.mesh.getWorldPosition(tmp);
        const depth = clamp01(1.25 - camera.position.distanceTo(tmp) / (baseDist() * 1.25));
        // On a phone only the changed part and the record you tap are named, so the sky stays legible.
        const shown = width < 640 ? (n.level === 0 || hovered ? 1 : 0) : n.level === 0 || hovered ? 1 : 0.35 + depth * 0.65;
        n.label.element.style.opacity = String(k * Math.max(n.dim, 0.12) * shown);
        n.label.element.classList.toggle("is-on", hovered);
      }
      for (const e of edges) {
        const k = reduceLive ? 1 : clamp01((t - (0.05 + e.level * STEP)) / 0.6);
        e.geo.instanceCount = Math.round(e.segments * k);
        const on = !litNow || (litNow.has(e.a) && litNow.has(e.b));
        const m = e.line.material as LineMaterial;
        m.opacity = litNow ? (on ? 0.95 : 0.04) : 0.42;
        m.linewidth = litNow && on ? 2.4 : 1.4;
      }
      orbitRings.forEach((ring) => {
        (ring.material as THREE.LineBasicMaterial).opacity = 0.22 * appear(ring.userData.level as number);
      });
      core.rotation.y = t * 0.25;
      core.rotation.x = Math.sin(t * 0.3) * 0.3;
      core.scale.setScalar(appear(0) * (1 + Math.sin(t * 2.2) * 0.05));
      stars.rotation.y = t * 0.006;

      if (pulses.visible) {
        edges.forEach((e, i) => {
          for (let k = 0; k < perEdge; k++) {
            const born = clamp01((t - (0.6 + e.level * STEP)) / 0.6);
            const u = ((t * 0.32 + k / perEdge + hash(e.a + e.b) * 0.5 - e.level * 0.12) % 1 + 1) % 1;
            const p = born > 0 ? e.curve.getPoint(u) : e.curve.getPoint(0);
            pulsePos.set([p.x, p.y, p.z], (i * perEdge + k) * 3);
          }
        });
        pulseGeo.attributes.position.needsUpdate = true;
      }
      waves.forEach((w, i) => {
        if (reduceLive) { (w.material as THREE.MeshBasicMaterial).opacity = 0; return; }
        const ph = ((t * 0.24 + i / waves.length) % 1);
        w.scale.setScalar(0.6 + ph * 19);
        (w.material as THREE.MeshBasicMaterial).opacity = t < 0.8 ? 0 : (quality.bloom ? 0.7 : 0.45) * Math.pow(1 - ph, 1.6);
      });

      // Clicking a record glides the camera to it; letting go drifts back out.
      const f = focusRef.current ? nodes.get(focusRef.current) : null;
      target.copy(f ? f.pos : new THREE.Vector3(0, 0, 0));
      controls.target.lerp(target, 0.06);
      const offset = camera.position.clone().sub(controls.target);
      const want = f ? baseDist() * 0.5 : baseDist();
      offset.setLength(offset.length() + (want - offset.length()) * 0.05);
      camera.position.copy(controls.target).add(offset);
      controls.autoRotateSpeed = f ? 0.2 : 0.55;
      controls.autoRotate = !reduceLive;
      controls.update();

      // The tooltip follows its record across the screen.
      const h = hoverRef.current ? nodes.get(hoverRef.current) : null;
      if (h && tip.current) {
        h.mesh.getWorldPosition(tmp);
        tmp.project(camera);
        tip.current.style.transform = `translate(${((tmp.x + 1) / 2) * width}px, ${((1 - tmp.y) / 2) * height}px) translate(-50%, calc(-100% - 18px))`;
      }
      if (quality.bloom) composer.render(); else renderer.render(scene, camera);
      labels.render(scene, camera);
    };
    loop();
    const raf = requestAnimationFrame(() => setReady(true));
    // Where a record is on screen right now, for the scripts that film the demo.
    const hook = window as unknown as { __constellation?: { at: (id: string) => { x: number; y: number } | null } };
    hook.__constellation = {
      at: (id: string) => {
        const n = nodes.get(id);
        if (!n) return null;
        const p = n.mesh.getWorldPosition(new THREE.Vector3()).project(camera);
        const b = renderer.domElement.getBoundingClientRect();
        return { x: b.left + ((p.x + 1) / 2) * b.width, y: b.top + ((1 - p.y) / 2) * b.height };
      },
    };

    return () => {
      cancelAnimationFrame(frame);
      cancelAnimationFrame(raf);
      delete hook.__constellation;
      ro.disconnect();
      io.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose?.();
        const mat = m.material as THREE.Material | THREE.Material[] | undefined;
        (Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((x) => x.dispose());
      });
      glow.dispose();
      composer.dispose();
      renderer.dispose();
      host.replaceChildren();
    };
  }, [r, g, byId]);

  // The chain under the pointer lights up and the rest steps back; the render loop applies it.
  useEffect(() => { litRef.current = lit; }, [lit]);

  const close = useCallback(() => setFocus(null), []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [close]);

  if (error) return null;
  const hovered = hover ? byId.get(hover) : null;
  const focused = focus ? byId.get(focus) : null;
  const neighbours = focused && g ? [...(g.parents.get(focused.id) ?? []), ...(g.children.get(focused.id) ?? [])]
    .map((id) => byId.get(id)).filter(Boolean) as GNode[] : [];

  return (
    <section data-tour="ripple" className="card no-reveal overflow-hidden" style={{ backdropFilter: "none", WebkitBackdropFilter: "none", background: "var(--panel)" }}>
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
        <div>
          <div className="flex items-center gap-2 text-[14px] font-semibold tracking-tight"><Waves size={15} className="text-accent" /> Watch one change ripple through Flyvi</div>
          <p className="mt-0.5 text-[13px] text-muted">
            {r ? <>A supplier raised the price and lead time of <span className="font-mono text-ink">{r.part.id}</span>. One FalkorDB traversal follows it through the company, ring by ring.</> : "Tracing the change through the company graph…"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => { setFocus(null); startRef.current = performance.now(); }}
                  className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12.5px] text-muted hover:border-line2 hover:text-ink">
            <RotateCcw size={13} /> Replay</button>
          <Link href={`/impact?source=${encodeURIComponent(NOTICE)}`} className="press flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-[12.5px] font-medium text-accent-ink hover:bg-accent-hover">
            Open the impact <ArrowRight size={13} /></Link>
        </div>
      </div>

      <div className="relative mx-3 mt-3 overflow-hidden rounded-xl border border-white/[0.06]" style={{ background: SKY }}>
        <div ref={mount} data-ripple-canvas className="relative w-full" style={{ height: 420 }}
             role="img" aria-label={r ? `Impact of the ${r.part.id} change across ${r.graph.nodes.length} records, as a 3D map` : "Loading the impact map"} />
        {!ready && <div className="pointer-events-none absolute inset-0 animate-pulse bg-white/[0.02]" />}
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_55%,rgba(4,6,12,0.85))]" />
        <div className="pointer-events-none absolute left-4 top-3 font-mono text-[10.5px] uppercase tracking-[0.22em] text-[#8ea3d8]/70">
          live · {r ? `${r.graph.nodes.length} records · ${r.graph.edges.length} links` : "tracing"}<span className="hidden sm:inline"> · drag to orbit</span>
        </div>

        <AnimatePresence>
          {hovered && hover !== focus && (
            <motion.div key={hovered.id} ref={tip} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}
                        className="pointer-events-none absolute left-0 top-0 z-10 max-w-[260px] rounded-xl border border-white/10 bg-[#0b1020]/90 px-3 py-2 text-[12.5px] text-white shadow-2xl backdrop-blur">
              <div className="flex items-center gap-1.5 font-medium"><span className="h-2 w-2 rounded-full" style={{ background: hex(hovered.type), boxShadow: `0 0 10px ${hex(hovered.type)}` }} />{hovered.label}</div>
              <div className="text-white/60">{KIND[hovered.type]?.label ?? hovered.type}{hovered.name && hovered.name !== hovered.label ? ` · ${hovered.name}` : ""}</div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {focused && (
            <motion.div key={focused.id} initial={{ opacity: 0, y: 12, filter: "blur(6px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                        exit={{ opacity: 0, y: 8, filter: "blur(4px)" }} transition={{ duration: 0.4, ease: EASE }}
                        className="absolute bottom-4 left-4 z-10 w-[min(320px,calc(100%-2rem))] rounded-2xl border border-white/10 bg-[#0b1020]/85 p-4 text-white shadow-2xl backdrop-blur-xl">
              <div className="flex items-start gap-2.5">
                <span className="mt-1 h-3 w-3 shrink-0 rounded-full" style={{ background: hex(focused.type), boxShadow: `0 0 14px ${hex(focused.type)}` }} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-[14px] font-semibold">{focused.label}</div>
                  <div className="text-[12px] text-white/60">{KIND[focused.type]?.label ?? focused.type}{focused.name && focused.name !== focused.label ? ` · ${focused.name}` : ""}{focused.role ? ` · ${focused.role}` : ""}</div>
                </div>
                <button onClick={close} aria-label="Close" className="rounded-md p-1 text-white/50 hover:bg-white/10 hover:text-white"><X size={14} /></button>
              </div>
              {neighbours.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {neighbours.slice(0, 8).map((x) => (
                    <button key={x.id} onClick={() => setFocus(x.id)} onMouseEnter={() => { hoverRef.current = x.id; setHover(x.id); }}
                            onMouseLeave={() => { hoverRef.current = null; setHover(null); }}
                            className="flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 font-mono text-[11px] text-white/80 hover:border-white/25 hover:text-white">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: hex(x.type) }} />{x.label}
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
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-5 py-3 text-[12px] text-muted">
          {Object.keys(LEGEND).filter((t) => counts[t]).map((t, i) => (
            <motion.span key={t} className="flex items-center gap-1.5" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                         transition={{ delay: reduce ? 0 : 0.3 + i * STEP, duration: 0.4, ease: EASE }}>
              <span className="h-2 w-2 rounded-full ring-1 ring-black/15" style={{ background: hex(t), boxShadow: `0 0 8px ${hex(t)}` }} />
              <span className="num font-semibold text-ink">{counts[t]}</span> {LEGEND[t]}
            </motion.span>
          ))}
          <span className="ml-auto hidden text-faint sm:inline">Drag to orbit · hover to trace a path · click to fly in</span>
          <span className="ml-auto text-faint sm:hidden">Tap a record to trace it</span>
        </div>
      )}
    </section>
  );
}
