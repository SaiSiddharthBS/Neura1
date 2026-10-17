"use client";

import { Check, Hash, Search, Users, X } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { Avatar } from "@/components/ViewerSwitch";
import type { Person } from "./types";

/** Pick one person for a direct message, several for a group, or name a new public channel. */
export default function NewConversation({ people, me, onClose, onDm, onGroup, onChannel, busy, error }: {
  people: Person[]; me: string; onClose: () => void; busy: boolean; error: string | null;
  onDm: (id: string) => void; onGroup: (name: string, ids: string[]) => void; onChannel: (name: string, purpose: string) => void;
}) {
  const [tab, setTab] = useState<"people" | "channel">("people");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");

  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);

  const list = useMemo(() => people.filter((p) => p.id !== me && (!q || `${p.name} ${p.role}`.toLowerCase().includes(q.toLowerCase()))), [people, me, q]);
  const byId = useMemo(() => new Map(people.map((p) => [p.id, p])), [people]);
  const toggle = (id: string) => setPicked((x) => (x.includes(id) ? x.filter((y) => y !== id) : [...x, id]));

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 backdrop-blur-sm" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <motion.div role="dialog" aria-label="New conversation" initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                  className="surface-pop flex max-h-[min(640px,90vh)] w-[min(460px,100%)] flex-col overflow-hidden">
        <div className="flex items-center gap-2 border-b border-line px-4 py-3">
          <div className="flex rounded-lg bg-elev p-0.5 text-[13px]">
            <button onClick={() => setTab("people")} className={`flex items-center gap-1.5 rounded-md px-3 py-1 ${tab === "people" ? "bg-panel font-medium text-ink shadow-sm" : "text-muted"}`}><Users size={13} /> People</button>
            <button onClick={() => setTab("channel")} className={`flex items-center gap-1.5 rounded-md px-3 py-1 ${tab === "channel" ? "bg-panel font-medium text-ink shadow-sm" : "text-muted"}`}><Hash size={13} /> Channel</button>
          </div>
          <button onClick={onClose} aria-label="Close" className="ml-auto rounded-md p-1 text-muted hover:bg-elev hover:text-ink"><X size={16} /></button>
        </div>

        {tab === "people" ? (
          <>
            <div className="space-y-2 px-4 pt-3">
              {picked.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {picked.map((id) => (
                    <button key={id} onClick={() => toggle(id)} className="flex items-center gap-1 rounded-full bg-accent/15 py-0.5 pl-1 pr-2 text-[12px] text-ink">
                      <Avatar name={byId.get(id)?.name ?? id} size={18} /> {byId.get(id)?.name} <X size={11} className="text-muted" />
                    </button>
                  ))}
                </div>
              )}
              <label className="flex items-center gap-2 rounded-xl border border-line bg-elev px-3 py-1.5 text-[13px] focus-within:border-accent/50">
                <Search size={14} className="text-faint" />
                <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search people"
                       className="min-w-0 flex-1 bg-transparent outline-none" style={{ background: "transparent" }} />
              </label>
            </div>
            <ul className="min-h-0 flex-1 overflow-y-auto p-2" data-lenis-prevent>
              {list.map((p) => {
                const on = picked.includes(p.id);
                return (
                  <li key={p.id}>
                    <button onClick={() => toggle(p.id)} onDoubleClick={() => onDm(p.id)}
                            className={`flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left hover:bg-elev ${on ? "bg-accent/10" : ""}`}>
                      <Avatar name={p.name} size={32} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13.5px] font-medium">{p.name}</span>
                        <span className="block truncate text-[11.5px] text-muted">{p.role}</span>
                      </span>
                      <span className={`grid h-5 w-5 place-items-center rounded-full border ${on ? "border-accent bg-accent text-accent-ink" : "border-line2"}`}>{on && <Check size={12} />}</span>
                    </button>
                  </li>
                );
              })}
              {!list.length && <li className="px-3 py-6 text-center text-[12.5px] text-muted">No one matches “{q}”.</li>}
            </ul>
            <div className="space-y-2 border-t border-line p-3">
              {picked.length > 1 && (
                <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder="Group name, e.g. PMIC bring-up"
                       className="w-full rounded-xl border border-line px-3 py-2 text-[13px]" />
              )}
              {error && <div className="text-[12px] text-warn">{error}</div>}
              <button disabled={busy || !picked.length || (picked.length > 1 && !name.trim())}
                      onClick={() => (picked.length === 1 ? onDm(picked[0]) : onGroup(name, picked))}
                      className="w-full rounded-xl bg-accent px-4 py-2 text-[13px] font-medium text-accent-ink transition hover:bg-accent-hover disabled:opacity-40">
                {picked.length === 0 ? "Choose one person, or several for a group"
                  : picked.length === 1 ? `Message ${byId.get(picked[0])?.name}`
                  : `Create group with ${picked.length} people`}
              </button>
            </div>
          </>
        ) : (
          <div className="space-y-3 p-4">
            <p className="text-[12.5px] text-muted">Channels are open to everyone at Flyvi, and what is said in them becomes company knowledge: searchable, linked to the parts and projects it names, and readable by Neura1.</p>
            <label className="block text-[12px] font-medium">Name
              <span className="mt-1 flex items-center gap-1.5 rounded-xl border border-line px-3 py-2 focus-within:border-accent/50">
                <Hash size={14} className="text-faint" />
                <input autoFocus value={name} onChange={(e) => setName(e.target.value)} maxLength={40} placeholder="pdu-48-bring-up"
                       className="min-w-0 flex-1 bg-transparent text-[13px] font-normal outline-none" style={{ background: "transparent" }} />
              </span>
            </label>
            <label className="block text-[12px] font-medium">What it is for <span className="font-normal text-faint">(optional)</span>
              <input value={purpose} onChange={(e) => setPurpose(e.target.value)} maxLength={140} placeholder="Bench work and results for the PDU-48"
                     className="mt-1 w-full rounded-xl border border-line px-3 py-2 text-[13px] font-normal" />
            </label>
            {error && <div className="text-[12px] text-warn">{error}</div>}
            <button disabled={busy || !name.trim()} onClick={() => onChannel(name, purpose)}
                    className="w-full rounded-xl bg-accent px-4 py-2 text-[13px] font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-40">Create channel</button>
          </div>
        )}
      </motion.div>
    </div>
  );
}
