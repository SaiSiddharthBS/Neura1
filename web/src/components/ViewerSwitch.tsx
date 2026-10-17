"use client";

import { Check, ChevronsUpDown, Search } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, viewerId } from "@/lib/api";

type P = { id: string; name: string; role: string; team: string };

export function Avatar({ name, size = 28 }: { name: string; size?: number }) {
  // A stable hue per person, so the same colleague always looks the same.
  const hue = [...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
  return (
    <span className="grid shrink-0 place-items-center rounded-full font-semibold text-white"
          style={{ width: size, height: size, fontSize: size * 0.42, background: `linear-gradient(135deg, oklch(0.62 0.15 ${hue}), oklch(0.5 0.16 ${(hue + 40) % 360}))` }}>
      {name.slice(0, 1).toUpperCase()}
    </span>
  );
}

/** Who the brain is acting for. Money and leave details follow this person's place in the graph. */
export default function ViewerSwitch() {
  const [people, setPeople] = useState<P[]>([]);
  const [me, setMe] = useState("P-HITHESH");
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setTimeout(() => setMe(viewerId()), 0);
    api<P[]>("/api/people").then(setPeople).catch(() => {});
  }, []);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  const current = people.find((p) => p.id === me);
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    const list = t ? people.filter((p) => `${p.name} ${p.role} ${p.team}`.toLowerCase().includes(t)) : people;
    const tier = (p: P) => (p.team === "Directors" ? 0 : p.team === "Leadership" ? 1 : 2);
    return [...list].sort((a, b) => tier(a) - tier(b) || a.name.localeCompare(b.name));
  }, [people, q]);

  function pick(id: string) {
    try { localStorage.setItem("neura1-viewer", id); } catch {}
    location.reload();
  }

  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="listbox"
              className="flex w-full items-center gap-2.5 rounded-lg px-1.5 py-1.5 text-left transition hover:bg-elev">
        <Avatar name={current?.name ?? "?"} />
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate text-[13px] font-medium">{current?.name ?? "…"}</span>
          <span className="block truncate text-[11.5px] text-muted">Viewing as · {current?.role ?? ""}</span>
        </span>
        <ChevronsUpDown size={14} className="text-faint" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: 6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 6, scale: 0.98 }}
                      transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                      className="surface-pop absolute bottom-full left-0 z-50 mb-2 w-[272px] overflow-hidden">
            <div className="border-b border-line p-2">
              <div className="flex items-center gap-2 rounded-lg bg-elev px-2">
                <Search size={13} className="text-faint" />
                <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="View the brain as…"
                       className="h-8 flex-1 bg-transparent text-[13px] outline-none" style={{ background: "transparent" }} />
              </div>
              <p className="mt-1.5 px-1 text-[11px] text-faint">What you see follows this person&apos;s place in the graph: money and leave plans for the directors and leadership; leave plans also for the person and their backup.</p>
            </div>
            <ul role="listbox" className="max-h-72 overflow-y-auto p-1">
              {shown.map((p) => (
                <li key={p.id}>
                  <button role="option" aria-selected={p.id === me} onClick={() => pick(p.id)}
                          className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-elev">
                    <Avatar name={p.name} size={24} />
                    <span className="min-w-0 flex-1 leading-tight">
                      <span className="block truncate text-[13px]">{p.name}</span>
                      <span className="block truncate text-[11px] text-muted">{p.role}</span>
                    </span>
                    {p.id === me && <Check size={14} className="text-accent" />}
                  </button>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
