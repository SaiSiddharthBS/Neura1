"use client";

import { useRouter } from "next/navigation";
import { ArrowRight, Box, Brain, FolderKanban, Search, Sparkles, User, Users, Zap } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";

type Hit = { id: string; label: string; name: string; kind: string | null };
type Cmd = { key: string; title: string; hint: string; icon: React.ElementType; go: () => void };

const PAGES = [
  ["Overview", "/"], ["Signals", "/signals"], ["Workboard", "/board"], ["Plans", "/history"], ["Ask & search", "/brain"],
  ["People", "/people"], ["Projects", "/projects"], ["Customers", "/customers"], ["Risk radar", "/risk"],
  ["What's new", "/changes"], ["Import", "/import"],
];

export default function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); }
      if (e.key === "Escape") setOpen(false);
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("neura1:palette", onOpen);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("neura1:palette", onOpen); };
  }, []);

  useEffect(() => { if (open) setTimeout(() => input.current?.focus(), 10); }, [open]);

  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(() => api<Hit[]>(`/api/lookup?q=${encodeURIComponent(q.trim())}`).then(setHits).catch(() => setHits([])), 120);
    return () => clearTimeout(t);
  }, [q]);

  const cmds: Cmd[] = useMemo(() => {
    const go = (href: string) => () => { setOpen(false); setQ(""); router.push(href); };
    const text = q.trim();
    const list: Cmd[] = [];
    if (text) {
      list.push({ key: "ask", title: `Ask the brain: “${text}”`, hint: "Answer with sources", icon: Sparkles, go: go(`/brain?ask=${encodeURIComponent(text)}`) });
      list.push({ key: "who", title: `Who knows about “${text}”`, hint: "Ranked people with reasons", icon: Users, go: go(`/brain?who=${encodeURIComponent(text)}`) });
    }
    for (const h of text.length >= 2 ? hits : []) {
      if (h.label === "Item" && (h.kind === "part" || h.kind === "assembly"))
        list.push({ key: `impact-${h.id}`, title: `Trace impact of ${h.id}`, hint: h.name, icon: Zap, go: go(`/impact?item=${encodeURIComponent(h.id)}`) });
      if (h.label === "Customer") list.push({ key: h.id, title: h.name, hint: "Customer", icon: Box, go: go(`/customers?id=${h.id}`) });
      else if (h.label === "Person") list.push({ key: h.id, title: h.name, hint: "Person", icon: User, go: go(`/people?id=${h.id}`) });
      else if (h.label === "Project") list.push({ key: h.id, title: h.name, hint: "Project", icon: FolderKanban, go: go(`/projects?id=${h.id}`) });
      else list.push({ key: `w-${h.id}`, title: `${h.id}`, hint: `${h.label} · ${h.name} · who knows`, icon: Box, go: go(`/brain?who=${encodeURIComponent(h.id)}`) });
    }
    for (const [title, href] of PAGES)
      if (!text || title.toLowerCase().includes(text.toLowerCase()))
        list.push({ key: href, title, hint: "Go to page", icon: ArrowRight, go: go(href) });
    return list.slice(0, 12);
  }, [q, hits, router]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-[12vh] backdrop-blur-sm" onClick={() => setOpen(false)}>
      <div className="card w-full max-w-xl overflow-hidden glow" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Search size={16} className="text-muted" />
          <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setSel(0); }}
                 onKeyDown={(e) => {
                   if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, cmds.length - 1)); }
                   if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
                   if (e.key === "Enter") cmds[sel]?.go();
                 }}
                 placeholder="Search parts, people, projects, or ask anything…"
                 className="h-14 flex-1 bg-transparent text-[15px] outline-none" style={{ background: "transparent" }} />
          <kbd className="rounded border border-line px-1.5 font-mono text-[11px] text-muted">esc</kbd>
        </div>
        <ul className="max-h-[50vh] overflow-y-auto p-2">
          {cmds.map((c, i) => (
            <li key={c.key}>
              <button onMouseEnter={() => setSel(i)} onClick={c.go}
                      className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${i === sel ? "bg-accent/15" : ""}`}>
                <c.icon size={16} className={i === sel ? "text-accent-hover" : "text-muted"} />
                <span className="flex-1 truncate">{c.title}</span>
                <span className="truncate text-xs text-muted">{c.hint}</span>
              </button>
            </li>
          ))}
          {!cmds.length && <li className="px-3 py-6 text-center text-sm text-muted"><Brain className="mx-auto mb-2" size={18} />Nothing matches.</li>}
        </ul>
      </div>
    </div>
  );
}
