"use client";

import { Hash, Lock, PenSquare, Search, Users, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Avatar } from "@/components/ViewerSwitch";
import { api } from "@/lib/api";
import { type Conversation, type Hit, when } from "./types";

export function ConversationAvatar({ c, me, size = 38 }: { c: Conversation; me: string; size?: number }) {
  if (c.kind === "channel") {
    return <span className="grid shrink-0 place-items-center rounded-xl bg-elev-strong text-muted" style={{ width: size, height: size }}><Hash size={size * 0.42} /></span>;
  }
  if (c.kind === "dm") {
    const other = c.members.find((m) => m.id !== me) ?? c.members[0];
    return (
      <span className="relative shrink-0">
        <Avatar name={other?.name ?? c.name} size={size} />
        {other?.online && <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-[var(--bg)] bg-success" aria-label="online" />}
      </span>
    );
  }
  const [a, b] = c.members.filter((m) => m.id !== me);
  return (
    <span className="relative shrink-0" style={{ width: size, height: size }}>
      <span className="absolute left-0 top-0"><Avatar name={a?.name ?? c.name} size={size * 0.68} /></span>
      <span className="absolute bottom-0 right-0 rounded-full ring-2 ring-[var(--bg)]"><Avatar name={b?.name ?? "+"} size={size * 0.68} /></span>
    </span>
  );
}

function Row({ c, me, active, onOpen }: { c: Conversation; me: string; active: boolean; onOpen: () => void }) {
  const p = c.preview;
  const preview = !p ? (c.purpose ?? "No messages yet")
    : p.kind === "system" ? p.text
    : p.mine ? `You: ${p.text}`
    : c.kind === "dm" && p.author !== "Neura1" ? p.text
    : `${p.author}: ${p.text}`;
  return (
    <button onClick={onOpen} aria-current={active ? "true" : undefined}
            className={`group flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left transition-colors ${active ? "bg-accent/12 ring-1 ring-accent/25" : "hover:bg-elev"}`}>
      <ConversationAvatar c={c} me={me} />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline gap-2">
          <span className={`flex min-w-0 items-center gap-1 truncate text-[13.5px] ${c.unread ? "font-semibold text-ink" : "font-medium text-ink"}`}>
            {c.name}
            {c.kind === "channel" && c.id === "chat/leadership" && <Lock size={11} className="shrink-0 text-faint" />}
            {c.kind === "group" && <Users size={11} className="shrink-0 text-faint" />}
          </span>
          <span className={`ml-auto shrink-0 text-[11px] tabular-nums ${c.unread ? "text-accent" : "text-faint"}`}>{when(c.last)}</span>
        </span>
        <span className="mt-0.5 flex items-center gap-2">
          <span className={`min-w-0 flex-1 truncate text-[12.5px] ${c.unread ? "text-ink-soft" : "text-muted"}`}>{preview}</span>
          {c.mentions > 0 && <span className="grid h-[18px] min-w-[18px] place-items-center rounded-full bg-warn/20 px-1 text-[10.5px] font-semibold text-warn">@</span>}
          {c.unread > 0 && <span className="num grid h-[18px] min-w-[18px] place-items-center rounded-full bg-accent px-1.5 text-[10.5px] font-semibold text-accent-ink">{c.unread > 99 ? "99+" : c.unread}</span>}
        </span>
      </span>
    </button>
  );
}

export default function ConversationList({ conversations, me, current, onOpen, onNew, onHit }: {
  conversations: Conversation[]; me: string; current: string; onOpen: (id: string) => void; onNew: () => void;
  onHit: (h: Hit) => void;
}) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);

  useEffect(() => {
    const term = q.trim();
    const t = setTimeout(() => {
      if (term.length < 2) { setHits([]); return; }
      api<Hit[]>(`/api/chat/search?q=${encodeURIComponent(term)}`).then(setHits).catch(() => setHits([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const match = (c: Conversation) => !q.trim() || `${c.name} ${c.members.map((m) => m.name).join(" ")}`.toLowerCase().includes(q.trim().toLowerCase());
  const chans = conversations.filter((c) => c.kind === "channel" && match(c));
  const direct = conversations.filter((c) => c.kind !== "channel" && match(c));

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 px-4 pb-2 pt-4">
        <h2 className="text-[17px] font-semibold tracking-tight">Chat</h2>
        <button onClick={onNew} title="New conversation" aria-label="New conversation"
                className="ml-auto grid h-8 w-8 place-items-center rounded-lg text-muted transition hover:bg-elev hover:text-ink"><PenSquare size={16} /></button>
      </div>
      <div className="px-3 pb-2">
        <label className="flex items-center gap-2 rounded-xl border border-line bg-elev px-3 py-1.5 text-[13px] focus-within:border-accent/50">
          <Search size={14} className="text-faint" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search people and messages"
                 className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-faint" style={{ background: "transparent" }} />
          {q && <button onClick={() => setQ("")} aria-label="Clear search" className="text-faint hover:text-ink"><X size={13} /></button>}
        </label>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-2 pb-3" data-lenis-prevent>
        {chans.length > 0 && (
          <div>
            <div className="px-2.5 pb-1 pt-1 text-[11px] font-medium text-faint">Channels</div>
            {chans.map((c) => <Row key={c.id} c={c} me={me} active={c.id === current} onOpen={() => onOpen(c.id)} />)}
          </div>
        )}
        <div>
          <div className="px-2.5 pb-1 pt-1 text-[11px] font-medium text-faint">Direct messages and groups</div>
          {direct.map((c) => <Row key={c.id} c={c} me={me} active={c.id === current} onOpen={() => onOpen(c.id)} />)}
          {!direct.length && !q && (
            <button onClick={onNew} className="mx-2.5 mt-1 text-left text-[12.5px] text-muted hover:text-ink">Start a conversation with anyone at Flyvi →</button>
          )}
        </div>
        {hits.length > 0 && (
          <div>
            <div className="px-2.5 pb-1 pt-1 text-[11px] font-medium text-faint">Messages</div>
            {hits.map((h) => (
              <button key={h.id} onClick={() => onHit(h)} className="block w-full rounded-xl px-2.5 py-2 text-left hover:bg-elev">
                <span className="flex items-baseline gap-2 text-[12px] text-muted">
                  <span className="truncate font-medium text-ink">{h.author}</span>
                  <span className="truncate">in {h.kind_of_channel === "channel" ? `#${h.channel_name}` : h.channel_name}</span>
                  <span className="ml-auto shrink-0 text-faint">{when(h.ts)}</span>
                </span>
                <span className="mt-0.5 line-clamp-2 text-[12.5px] text-ink-soft">{h.text}</span>
              </button>
            ))}
          </div>
        )}
        {q.trim().length >= 2 && !hits.length && !chans.length && !direct.length && (
          <div className="px-3 py-6 text-center text-[12.5px] text-muted">Nothing matches “{q.trim()}”.</div>
        )}
      </div>
    </div>
  );
}
