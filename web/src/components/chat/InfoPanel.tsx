"use client";

import Link from "next/link";
import { Check, LogOut, Pencil, UserMinus, UserPlus, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Avatar } from "@/components/ViewerSwitch";
import { ConversationAvatar } from "./ConversationList";
import type { Conversation, Person } from "./types";

/** Details of the open conversation: who is in it, and for groups, adding, removing, renaming and leaving. */
export default function InfoPanel({ c, me, people, onClose, onRename, onAdd, onRemove }: {
  c: Conversation; me: string; people: Person[]; onClose: () => void;
  onRename: (name: string, purpose: string) => Promise<void>; onAdd: (ids: string[]) => Promise<void>; onRemove: (id: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(c.name);
  const [purpose, setPurpose] = useState(c.purpose ?? "");
  const [adding, setAdding] = useState(false);
  const [q, setQ] = useState("");
  const [leaving, setLeaving] = useState(false);
  const role = useMemo(() => new Map(people.map((p) => [p.id, p.role])), [people]);
  const canEdit = (c.kind === "group") || (c.kind === "channel" && !c.default && c.created_by === me);
  const other = c.kind === "dm" ? c.members.find((m) => m.id !== me) : null;
  const candidates = people.filter((p) => !c.members.some((m) => m.id === p.id) && (!q || p.name.toLowerCase().includes(q.toLowerCase())));

  return (
    <aside className="flex h-full min-h-0 flex-col">
      <div className="flex items-center border-b border-line px-4 py-3">
        <span className="text-[13.5px] font-semibold">{c.kind === "dm" ? "Contact" : c.kind === "group" ? "Group" : c.kind === "bot" ? "Neura1" : "Channel"} details</span>
        <button onClick={onClose} aria-label="Close details" className="ml-auto rounded-md p-1 text-muted hover:bg-elev hover:text-ink"><X size={15} /></button>
      </div>
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4" data-lenis-prevent>
        <div className="flex flex-col items-center gap-2 text-center">
          <ConversationAvatar c={c} me={me} size={64} />
          {editing ? (
            <div className="w-full space-y-2">
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} className="w-full rounded-lg border border-line px-2.5 py-1.5 text-[13px]" aria-label="Name" />
              {c.kind === "channel" && <input value={purpose} onChange={(e) => setPurpose(e.target.value)} maxLength={140} placeholder="What it is for" className="w-full rounded-lg border border-line px-2.5 py-1.5 text-[13px]" aria-label="Description" />}
              <div className="flex justify-center gap-2">
                <button onClick={() => setEditing(false)} className="rounded-lg px-3 py-1 text-[12.5px] text-muted hover:bg-elev">Cancel</button>
                <button onClick={async () => { await onRename(name, purpose); setEditing(false); }} className="flex items-center gap-1 rounded-lg bg-accent px-3 py-1 text-[12.5px] text-accent-ink"><Check size={13} /> Save</button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-1.5 text-[16px] font-semibold">{c.kind === "channel" ? `#${c.name}` : c.name}
                {canEdit && <button onClick={() => setEditing(true)} aria-label="Rename" className="rounded p-1 text-faint hover:bg-elev hover:text-ink"><Pencil size={12} /></button>}</div>
              {c.purpose && <p className="text-[12.5px] text-muted">{c.purpose}</p>}
              {other && <p className="text-[12.5px] text-muted">{role.get(other.id) ?? ""}{other.online ? " · online" : ""}</p>}
              {other && <Link href={`/people?id=${other.id}`} className="text-[12.5px] text-accent hover:underline">Open profile →</Link>}
            </>
          )}
        </div>

        {c.kind === "channel" && (
          <p className="rounded-xl bg-elev p-3 text-[12px] text-muted">
            {c.id === "chat/leadership" ? "Open to the directors and the leadership team. Amounts are shown here." : "Open to everyone at Flyvi. Messages become company knowledge; amounts are hidden from people who may not see them."}
          </p>
        )}
        {c.kind === "bot" && (
          <p className="rounded-xl bg-elev p-3 text-[12px] text-muted">Only you can read this conversation. Neura1 posts your brief here every morning at 09:00, and answers anything you write, with sources and only what you may see.</p>
        )}
        {c.kind !== "channel" && c.kind !== "bot" && (
          <p className="rounded-xl bg-elev p-3 text-[12px] text-muted">Private to its members. These messages never become company knowledge and never appear in anyone else&apos;s search.</p>
        )}

        {c.kind === "group" && (
          <div>
            <div className="mb-1.5 flex items-center text-[12px] font-medium text-faint">{c.members.length} members
              <button onClick={() => setAdding((x) => !x)} className="ml-auto flex items-center gap-1 rounded-md px-1.5 py-0.5 text-accent hover:bg-elev"><UserPlus size={13} /> Add</button>
            </div>
            {adding && (
              <div className="mb-2 rounded-xl border border-line p-2">
                <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search people" className="mb-1 w-full rounded-lg border border-line px-2 py-1 text-[12.5px]" />
                <div className="max-h-44 overflow-y-auto" data-lenis-prevent>
                  {candidates.map((p) => (
                    <button key={p.id} onClick={async () => { await onAdd([p.id]); setQ(""); }} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12.5px] hover:bg-elev">
                      <Avatar name={p.name} size={22} /> {p.name} <UserPlus size={12} className="ml-auto text-faint" />
                    </button>
                  ))}
                  {!candidates.length && <div className="px-2 py-2 text-[12px] text-muted">Everyone is already here.</div>}
                </div>
              </div>
            )}
            <ul className="space-y-0.5">
              {c.members.map((m) => (
                <li key={m.id} className="group flex items-center gap-2.5 rounded-lg px-1.5 py-1.5 hover:bg-elev">
                  <span className="relative"><Avatar name={m.name} size={28} />{m.online && <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[var(--bg)] bg-success" />}</span>
                  <Link href={`/people?id=${m.id}`} className="min-w-0 flex-1 truncate text-[13px] hover:underline">{m.name}{m.id === me ? " (you)" : ""}</Link>
                  {c.created_by === m.id && <span className="text-[10.5px] text-faint">created it</span>}
                  {c.created_by === me && m.id !== me && (
                    <button onClick={() => onRemove(m.id)} aria-label={`Remove ${m.name}`} className="rounded p-1 text-faint opacity-0 hover:text-danger group-hover:opacity-100"><UserMinus size={13} /></button>
                  )}
                </li>
              ))}
            </ul>
            <div className="mt-4">
              {leaving ? (
                <div className="flex items-center gap-2 text-[12.5px]">
                  <span className="text-muted">Leave {c.name}?</span>
                  <button onClick={() => setLeaving(false)} className="ml-auto rounded-md px-2 py-1 text-muted hover:bg-elev">Stay</button>
                  <button onClick={() => onRemove(me)} className="rounded-md bg-danger/15 px-2 py-1 font-medium text-danger">Leave</button>
                </div>
              ) : (
                <button onClick={() => setLeaving(true)} className="flex items-center gap-1.5 text-[12.5px] text-danger hover:underline"><LogOut size={13} /> Leave group</button>
              )}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
