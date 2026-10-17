"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowDown, ArrowLeft, Bot, Check, CheckCheck, Copy, CornerUpLeft, FileText, Hash, Info, Link2, Loader2, Pencil,
  SendHorizontal, Smile, Sparkles, Trash2, X,
} from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import { Avatar } from "@/components/ViewerSwitch";
import ConversationList, { ConversationAvatar } from "@/components/chat/ConversationList";
import InfoPanel from "@/components/chat/InfoPanel";
import NewConversation from "@/components/chat/NewConversation";
import {
  BOT, type Conversation, dayLabel, type Hit, type Msg, parseJson, type Person, REACTIONS, type Thread, time,
} from "@/components/chat/types";
import { api, ApiError, viewerId } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";

const COMMANDS = [
  ["/impact NB54360 320 22", "Trace a part change through the company"],
  ["/who CAN bus", "Who knows about something, and why"],
  ["/away Raghavendra", "What changes while someone is away"],
  ["/risk", "Where the company is fragile right now"],
  ["/help", "Everything Neura1 can do in chat"],
];

const LINK_FOR: Record<string, (id: string) => string> = {
  Person: (id) => `/people?id=${id}`, Project: (id) => `/projects?id=${id}`, Customer: (id) => `/customers?id=${id}`,
};

function errorText(e: unknown): string {
  if (e instanceof ApiError && e.body && typeof e.body === "object" && "detail" in e.body) return String((e.body as { detail: unknown }).detail);
  return (e as Error).message;
}

/** Bold, code, links, and @mentions of people or Neura1. */
function rich(text: string, names: string[], mine: boolean) {
  const people = names.length ? names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") : "\\u0000";
  const re = new RegExp(`(\\*\\*[^*]+\\*\\*|\`[^\`]+\`|https?://[^\\s)]+|@neura1\\b|@(?:${people})\\b)`, "gi");
  return text.split(re).map((part, i) => {
    if (!part) return null;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <b key={i}>{part.slice(2, -2)}</b>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={i} className={`rounded px-1 font-mono text-[12px] ${mine ? "bg-black/15" : "bg-elev-strong"}`}>{part.slice(1, -1)}</code>;
    if (/^https?:\/\//.test(part)) return <a key={i} href={part} target="_blank" rel="noreferrer" className="underline underline-offset-2">{part}</a>;
    if (/^@neura1$/i.test(part)) return <span key={i} className={`rounded px-1 ${mine ? "bg-white/20" : "bg-cyan/15 text-cyan"}`}>@neura1</span>;
    if (part.startsWith("@") && new RegExp(`^@(?:${people})$`, "i").test(part)) return <span key={i} className={`rounded px-1 font-medium ${mine ? "bg-white/20" : "bg-accent/15 text-accent"}`}>{part}</span>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

type Group = { day: string; author: string; author_id: string | null; kind: string; items: Msg[] };

/** Consecutive messages by the same person within five minutes read as one block, as in any messenger. */
function grouped(msgs: Msg[]): Group[] {
  const out: Group[] = [];
  for (const m of msgs) {
    const day = dayLabel(m.ts);
    const g = out[out.length - 1];
    const close = g && g.day === day && g.author === m.author && g.kind !== "system" && m.kind !== "system" &&
      new Date(m.ts).getTime() - new Date(g.items[g.items.length - 1].ts).getTime() < 5 * 60_000;
    if (close) g.items.push(m);
    else out.push({ day, author: m.author, author_id: m.author_id, kind: m.kind === "system" ? "system" : "message", items: [m] });
  }
  return out;
}

export default function ChatView() {
  const params = useSearchParams();
  const router = useRouter();
  const routed = params.get("c");
  const current = routed ?? "chat/general";
  const focus = params.get("m");
  const me = useMemo(() => viewerId(), []);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [typing, setTyping] = useState<string[]>([]);
  const [readState, setReadState] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [text, setText] = useState("");
  const [reply, setReply] = useState<Msg | null>(null);
  const [editing, setEditing] = useState<Msg | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState(false);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<string | null>(null);
  const [below, setBelow] = useState(0);
  const [flash, setFlash] = useState<string | null>(null);
  const [mention, setMention] = useState<{ at: number; q: string } | null>(null);
  const [hint, setHint] = useState(0);
  const [divider, setDivider] = useState<string | null>(null);

  const scroller = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const cursor = useRef<string | null>(null);
  const atBottom = useRef(true);
  const lastTyping = useRef(0);
  const lastRead = useRef("");
  const known = useRef<Map<string, number> | null>(null);
  const openedWith = useRef<number>(0);

  const conv = conversations.find((c) => c.id === current);
  const names = useMemo(() => people.map((p) => p.name), [people]);
  const roleOf = useMemo(() => new Map(people.map((p) => [p.id, p.role])), [people]);

  const open = useCallback((id: string, message?: string) => {
    router.replace(`/chat?c=${encodeURIComponent(id)}${message ? `&m=${encodeURIComponent(message)}` : ""}`);
  }, [router]);

  // ---------- conversations, with a toast for anything new elsewhere ----------
  const loadConversations = useCallback(async () => {
    try {
      const cs = await api<Conversation[]>("/api/chat/channels");
      setConversations(cs);
      const before = known.current;
      if (before) {
        for (const c of cs) {
          const had = before.get(c.id) ?? 0;
          if (c.id !== current && c.unread > had && c.preview && !c.preview.mine && c.preview.kind !== "system") {
            toast(c.kind === "channel" ? `#${c.name}` : c.name, {
              description: `${c.kind === "dm" ? "" : `${c.preview.author}: `}${c.preview.text}`.slice(0, 120),
              action: { label: "Open", onClick: () => open(c.id) },
            });
          }
        }
      }
      known.current = new Map(cs.map((c) => [c.id, c.unread]));
    } catch { /* the list refreshes on the next tick */ }
  }, [current, open]);

  useEffect(() => {
    api<Person[]>("/api/people").then(setPeople).catch(() => {});
    const first = setTimeout(loadConversations, 0);
    const t = setInterval(loadConversations, 4000);
    return () => { clearTimeout(first); clearInterval(t); };
  }, [loadConversations]);

  // The tab title carries the unread count, like any messenger.
  useEffect(() => {
    const total = conversations.reduce((n, c) => n + c.unread, 0);
    const base = "Chat · Neura1";
    document.title = total ? `(${total}) ${base}` : base;
  }, [conversations]);

  // ---------- the open conversation ----------
  const markRead = useCallback((latest: string | undefined) => {
    if (!latest || latest <= lastRead.current || document.visibilityState !== "visible") return;
    lastRead.current = latest;
    api("/api/chat/read", { method: "POST", body: JSON.stringify({ channel: current }) })
      .then(() => setConversations((cs) => cs.map((c) => (c.id === current ? { ...c, unread: 0, mentions: 0 } : c))))
      .catch(() => {});
  }, [current]);

  const tick = useCallback(async () => {
    try {
      const q = `/api/chat/messages?channel=${encodeURIComponent(current)}${cursor.current ? `&after=${encodeURIComponent(cursor.current)}` : ""}`;
      const r = await api<Thread>(q);
      const first = cursor.current === null;
      cursor.current = r.cursor;
      setTyping(r.typing);
      setReadState(r.read);
      if (first) {
        setMsgs(r.messages);
        // Where "New messages" starts: just before the unread messages from other people.
        const unread = openedWith.current;
        if (unread > 0) {
          const theirs = r.messages.filter((m) => m.author_id !== me && m.kind !== "system");
          setDivider(theirs[Math.max(0, theirs.length - unread)]?.id ?? null);
        }
        setLoaded(true);
      } else if (r.messages.length) {
        setMsgs((old) => {
          const byId = new Map(old.map((m) => [m.id, m]));
          let added = 0;
          for (const m of r.messages) { if (!byId.has(m.id) && m.author_id !== me) added++; byId.set(m.id, m); }
          if (added && !atBottom.current) setBelow((n) => n + added);
          return [...byId.values()].sort((a, b) => a.ts.localeCompare(b.ts));
        });
        if (r.messages.some((m) => m.author === BOT && (m.kind === "answer" || m.kind === "error"))) setWaiting(false);
      }
      const theirs = r.messages.filter((m) => m.author_id !== me);
      markRead(theirs.length ? theirs[theirs.length - 1].ts : first && r.messages.length ? r.messages[r.messages.length - 1].ts : undefined);
      setError(null);
    } catch (e) {
      setError(errorText(e));
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) setLoaded(true);
    }
  }, [current, me, markRead]);

  useEffect(() => {
    cursor.current = null;
    lastRead.current = "";
    atBottom.current = true;
    openedWith.current = known.current?.get(current) ?? 0;
    const reset = setTimeout(() => {
      setMsgs([]); setLoaded(false); setReply(null); setEditing(null); setText(""); setBelow(0); setDivider(null);
      setWaiting(false); setTyping([]); setError(null); setMention(null);
      tick();
    }, 0);
    const t = setInterval(tick, 2000);
    const back = () => { if (document.visibilityState === "visible") tick(); };
    document.addEventListener("visibilitychange", back);
    return () => { clearTimeout(reset); clearInterval(t); document.removeEventListener("visibilitychange", back); };
  }, [current, tick]);

  // ---------- scrolling ----------
  const toBottom = useCallback((smooth = true) => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    setBelow(0);
  }, []);

  useEffect(() => {
    if (!loaded) return;
    const el = scroller.current;
    if (!el) return;
    const target = focus ? document.getElementById(`msg-${CSS.escape(focus)}`) : divider ? document.getElementById(`msg-${CSS.escape(divider)}`) : null;
    if (target) {
      target.scrollIntoView({ block: "center" });
      if (focus) { setTimeout(() => setFlash(focus), 0); setTimeout(() => setFlash(null), 2200); }
    } else el.scrollTop = el.scrollHeight;
    // Only when a conversation finishes loading.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, current]);

  useEffect(() => {
    if (loaded && atBottom.current) toBottom(true);
  }, [msgs.length, typing.length, waiting, loaded, toBottom]);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (atBottom.current && below) setBelow(0);
  };

  const jumpTo = (id: string) => {
    const el = document.getElementById(`msg-${CSS.escape(id)}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlash(id);
    setTimeout(() => setFlash(null), 1800);
  };

  // ---------- writing ----------
  const write = async <T,>(path: string, init: RequestInit): Promise<T | null> => {
    if (!credentials()) return null;
    try {
      return await api<T>(path, { ...init, write: true });
    } catch (e) {
      if (e instanceof ApiError && e.status === 403 && String(errorText(e)).toLowerCase().includes("passcode")) forgetPasscode();
      setError(errorText(e));
      return null;
    }
  };

  const resize = () => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  };
  useEffect(resize, [text]);

  async function send() {
    const body = text.trim();
    if (!body) return;
    setMention(null);
    if (editing) {
      const id = editing.id;
      setText(""); setEditing(null);
      const r = await write<{ edited_at: string }>("/api/chat/messages", { method: "PATCH", body: JSON.stringify({ id, text: body }) });
      if (r) setMsgs((ms) => ms.map((m) => (m.id === id ? { ...m, text: body, edited_at: r.edited_at } : m)));
      else setText(body);
      return;
    }
    const replyTo = reply?.id ?? null;
    setText(""); setReply(null);
    atBottom.current = true;
    const r = await write<{ thinking?: boolean }>("/api/chat/messages", { method: "POST", body: JSON.stringify({ channel: current, text: body, reply_to: replyTo }) });
    if (!r) { setText(body); return; }
    if (r.thinking) setWaiting(true);
    tick();
    loadConversations();
  }

  function onType(v: string) {
    setText(v);
    setHint(0);
    const caret = box.current?.selectionStart ?? v.length;
    const m = /(^|\s)@([\w-]*)$/.exec(v.slice(0, caret));
    setMention(m ? { at: caret - m[2].length - 1, q: m[2].toLowerCase() } : null);
    const now = Date.now();
    if (v.trim() && now - lastTyping.current > 3000) {
      lastTyping.current = now;
      api("/api/chat/typing", { method: "POST", body: JSON.stringify({ channel: current }) }).catch(() => {});
    }
  }

  const mentionPool = useMemo(() => {
    const pool = conv && conv.kind !== "channel" ? conv.members.filter((m) => m.id !== me).map((m) => m.name) : people.filter((p) => p.id !== me).map((p) => p.name);
    return ["neura1", ...pool];
  }, [conv, people, me]);
  const mentions = mention === null ? [] : mentionPool.filter((n) => n.toLowerCase().startsWith(mention.q)).slice(0, 6);
  const commands = text.startsWith("/") && !text.includes(" ") ? COMMANDS.filter(([c]) => c.startsWith(text.split(" ")[0])) : [];

  function pickMention(name: string) {
    if (!mention) return;
    const at = mention.at;
    const caret = box.current?.selectionStart ?? text.length;
    setText(`${text.slice(0, at)}@${name} ${text.slice(caret)}`);
    setMention(null);
    requestAnimationFrame(() => { box.current?.focus(); const p = at + name.length + 2; box.current?.setSelectionRange(p, p); });
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    const list = mentions.length ? mentions : commands.map(([c]) => c);
    if (list.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      setHint((h) => (h + (e.key === "ArrowDown" ? 1 : list.length - 1)) % list.length);
      return;
    }
    if (list.length && (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey && mentions.length))) {
      e.preventDefault();
      if (mentions.length) pickMention(mentions[hint % mentions.length]);
      else setText(commands[hint % commands.length][0]);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); return; }
    if (e.key === "Escape") { setReply(null); if (editing) { setEditing(null); setText(""); } return; }
    if (e.key === "ArrowUp" && !text) {
      const mine = [...msgs].reverse().find((m) => m.author_id === me && !m.deleted && m.kind === "message");
      if (mine) { e.preventDefault(); startEdit(mine); }
    }
  }

  function startEdit(m: Msg) {
    setReply(null);
    setEditing(m);
    setText(m.text);
    requestAnimationFrame(() => { box.current?.focus(); const n = m.text.length; box.current?.setSelectionRange(n, n); });
  }

  async function react(m: Msg, emoji: string) {
    // Show it at once; the next poll brings the authoritative state.
    setMsgs((ms) => ms.map((x) => {
      if (x.id !== m.id) return x;
      const who = new Set(x.reactions[emoji] ?? []);
      if (who.has(me)) who.delete(me); else who.add(me);
      const next = { ...x.reactions };
      if (who.size) next[emoji] = [...who]; else delete next[emoji];
      return { ...x, reactions: next };
    }));
    await write("/api/chat/react", { method: "POST", body: JSON.stringify({ id: m.id, emoji }) });
  }

  async function remove(m: Msg) {
    const r = await write("/api/chat/messages/delete", { method: "POST", body: JSON.stringify({ id: m.id }) });
    if (r) setMsgs((ms) => ms.map((x) => (x.id === m.id ? { ...x, deleted: true, text: "", reactions: {}, about: [] } : x)));
  }

  // ---------- new conversations and group changes ----------
  async function startDm(id: string) {
    setBusy(true); setDialogError(null);
    try {
      const r = await api<{ id: string }>("/api/chat/dm", { method: "POST", body: JSON.stringify({ person_id: id }) });
      setCreating(false);
      await loadConversations();
      open(r.id);
    } catch (e) { setDialogError(errorText(e)); } finally { setBusy(false); }
  }
  async function createGroup(name: string, members: string[]) {
    setBusy(true); setDialogError(null);
    try {
      if (!credentials()) return;
      const r = await api<{ id: string }>("/api/chat/groups", { method: "POST", write: true, body: JSON.stringify({ name, members }) });
      setCreating(false);
      await loadConversations();
      open(r.id);
    } catch (e) { setDialogError(errorText(e)); } finally { setBusy(false); }
  }
  async function createChannel(name: string, purpose: string) {
    setBusy(true); setDialogError(null);
    try {
      if (!credentials()) return;
      const r = await api<{ id: string }>("/api/chat/channels", { method: "POST", write: true, body: JSON.stringify({ name, purpose }) });
      setCreating(false);
      await loadConversations();
      open(r.id);
    } catch (e) { setDialogError(errorText(e)); } finally { setBusy(false); }
  }
  async function rename(name: string, purpose: string) {
    await write("/api/chat/channels", { method: "PATCH", body: JSON.stringify({ channel: current, name, purpose }) });
    await loadConversations();
    tick();
  }
  async function addPeople(ids: string[]) {
    await write("/api/chat/members", { method: "POST", body: JSON.stringify({ channel: current, add: ids }) });
    await loadConversations();
    tick();
  }
  async function removePerson(id: string) {
    const r = await write("/api/chat/members", { method: "POST", body: JSON.stringify({ channel: current, remove: id }) });
    await loadConversations();
    if (r && id === me) { setInfo(false); open("chat/general"); } else tick();
  }

  // ---------- read receipts ----------
  const lastMine = [...msgs].reverse().find((m) => m.author_id === me && !m.deleted && m.kind !== "system");
  const seenBy = lastMine && conv && conv.kind !== "channel"
    ? conv.members.filter((m) => m.id !== me && (readState[m.id] ?? "") >= lastMine.ts).map((m) => m.name)
    : [];

  const groups = grouped(msgs);
  const placeholder = conv
    ? `Message ${conv.kind === "channel" ? `#${conv.name}` : conv.name} · / for commands, @neura1 to ask`
    : "Message · / for commands, @neura1 to ask";
  const showList = !routed;

  return (
    <div className="-mb-12 flex h-[calc(100dvh-7rem)] min-h-[480px] gap-3">
      <aside className={`card min-h-0 w-full shrink-0 overflow-hidden md:block md:w-[300px] ${showList ? "block" : "hidden"}`}>
        <ConversationList conversations={conversations} me={me} current={current} onOpen={(id) => open(id)}
                          onNew={() => { setDialogError(null); setCreating(true); }} onHit={(h: Hit) => open(h.channel, h.id)} />
      </aside>

      <section className={`card min-h-0 min-w-0 flex-1 flex-col overflow-hidden md:flex ${showList ? "hidden" : "flex"}`}>
        <header className="flex items-center gap-3 border-b border-line px-4 py-2.5">
          <button onClick={() => router.replace("/chat")} aria-label="All conversations" className="rounded-lg p-1 text-muted hover:bg-elev md:hidden"><ArrowLeft size={18} /></button>
          {conv ? <ConversationAvatar c={conv} me={me} size={36} /> : <span className="grid h-9 w-9 place-items-center rounded-xl bg-elev-strong"><Hash size={15} /></span>}
          <button onClick={() => setInfo((x) => !x)} className="min-w-0 flex-1 text-left">
            <div className="truncate text-[14.5px] font-semibold">{conv ? (conv.kind === "channel" ? `#${conv.name}` : conv.name) : current.replace("chat/", "#")}</div>
            <div className="truncate text-[12px] text-muted">
              {typing.length ? <span className="text-accent">{typing.join(", ")} {typing.length > 1 ? "are" : "is"} typing…</span>
                : !conv ? "" : conv.kind === "channel" ? (conv.purpose ?? "Channel")
                : conv.kind === "dm" ? (() => { const o = conv.members.find((m) => m.id !== me); return o?.online ? "Online" : roleOf.get(o?.id ?? "") ?? ""; })()
                : conv.members.map((m) => (m.id === me ? "You" : m.name)).join(", ")}
            </div>
          </button>
          <span className="hidden items-center gap-1 text-[11px] text-muted lg:flex"><Sparkles size={12} className="text-cyan" /> @neura1 is here</span>
          <button onClick={() => setInfo((x) => !x)} aria-label="Conversation details" aria-pressed={info}
                  className={`rounded-lg p-1.5 ${info ? "bg-elev-strong text-ink" : "text-muted hover:bg-elev hover:text-ink"}`}><Info size={17} /></button>
        </header>

        <div className="relative min-h-0 flex-1">
          <div ref={scroller} onScroll={onScroll} className="h-full overflow-y-auto px-3 py-4 sm:px-5" data-lenis-prevent>
            {!loaded && <div className="grid h-full place-items-center text-muted"><Loader2 size={18} className="animate-spin" /></div>}
            {loaded && !msgs.length && !error && (
              <div className="grid h-full place-items-center px-6 text-center">
                <div className="max-w-sm space-y-2">
                  {conv && <div className="mx-auto w-fit"><ConversationAvatar c={conv} me={me} size={56} /></div>}
                  <div className="text-[15px] font-semibold">{conv?.kind === "dm" ? `This is the start of your conversation with ${conv.name}` : "No messages yet"}</div>
                  <p className="text-[13px] text-muted">Say hello, type <code className="rounded bg-elev px-1">/</code> for graph commands, or ask <span className="text-cyan">@neura1</span> anything about Flyvi.</p>
                </div>
              </div>
            )}
            {groups.map((g, gi) => {
              const newDay = gi === 0 || groups[gi - 1].day !== g.day;
              const mine = g.author_id === me;
              const bot = g.author === BOT;
              return (
                <Fragment key={g.items[0].id}>
                  {newDay && (
                    <div className="sticky top-0 z-10 my-3 flex justify-center">
                      <span className="rounded-full border border-line px-3 py-0.5 text-[11px] font-medium text-muted shadow-sm" style={{ background: "var(--bg)" }}>{g.day}</span>
                    </div>
                  )}
                  {g.kind === "system" ? (
                    g.items.map((m) => <div key={m.id} id={`msg-${m.id}`} className="my-2 text-center text-[11.5px] text-muted">{m.text} · {time(m.ts)}</div>)
                  ) : (
                    <div className={`mt-3 flex gap-2.5 ${mine ? "flex-row-reverse" : ""}`}>
                      {!mine && (bot
                        ? <span className="mt-5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-accent to-violet text-white"><Bot size={15} /></span>
                        : <span className="mt-5"><Avatar name={g.author} size={32} /></span>)}
                      <div className={`flex min-w-0 max-w-[min(680px,85%)] flex-col ${mine ? "items-end" : "items-start"}`}>
                        {!mine && (
                          <div className="mb-0.5 flex items-baseline gap-2 px-1 text-[12px]">
                            {g.author_id ? <Link href={`/people?id=${g.author_id}`} className="font-semibold hover:underline">{g.author}</Link> : <span className="font-semibold text-cyan">{g.author}</span>}
                            {bot && g.items[0].kind === "notice" && <span className="rounded bg-violet/15 px-1.5 text-[10px] text-violet">posted on its own</span>}
                          </div>
                        )}
                        {g.items.map((m, i) => (
                          <Fragment key={m.id}>
                            {divider === m.id && (
                              <div className="my-2 flex w-full items-center gap-2 text-[11px] font-medium text-danger"><span className="h-px flex-1 bg-danger/40" />New messages<span className="h-px flex-1 bg-danger/40" /></div>
                            )}
                            <Bubble m={m} me={me} mine={mine} bot={bot} last={i === g.items.length - 1} names={names} flash={flash === m.id}
                                    onReply={() => { setEditing(null); setReply(m); box.current?.focus(); }}
                                    onEdit={() => startEdit(m)} onDelete={() => remove(m)} onReact={(e) => react(m, e)}
                                    onJump={jumpTo} onEvidence={setEvidence} people={people} />
                          </Fragment>
                        ))}
                      </div>
                    </div>
                  )}
                </Fragment>
              );
            })}
            {seenBy.length > 0 && (
              <div className="mt-1 flex items-center justify-end gap-1 pr-1 text-[11px] text-muted">
                <CheckCheck size={13} className="text-accent" /> {conv?.kind === "dm" ? "Seen" : `Seen by ${seenBy.join(", ")}`}
              </div>
            )}
            {lastMine && !seenBy.length && conv && conv.kind !== "channel" && msgs[msgs.length - 1]?.id === lastMine.id && (
              <div className="mt-1 flex items-center justify-end gap-1 pr-1 text-[11px] text-faint"><Check size={13} /> Sent</div>
            )}
            {waiting && (
              <div className="mt-3 flex items-center gap-2.5">
                <span className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-accent to-violet text-white"><Bot size={15} /></span>
                <span className="flex items-center gap-2 rounded-2xl border border-cyan/25 bg-cyan/[0.07] px-3 py-2 text-[12.5px] text-muted"><Loader2 size={13} className="animate-spin" /> Neura1 is working through the graph…</span>
              </div>
            )}
            {typing.length > 0 && (
              <div className="mt-3 flex items-center gap-2 pl-1 text-[12px] text-muted">
                <span className="flex gap-0.5 rounded-full bg-elev px-2.5 py-2">
                  {[0, 1, 2].map((i) => <motion.span key={i} className="h-1.5 w-1.5 rounded-full bg-muted" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1, repeat: Infinity, delay: i * 0.18 }} />)}
                </span>
                {typing.join(", ")} {typing.length > 1 ? "are" : "is"} typing
              </div>
            )}
          </div>
          <AnimatePresence>
            {below > 0 && (
              <motion.button initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }} onClick={() => toBottom(true)}
                             className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-ink shadow-lg">
                <ArrowDown size={13} /> {below} new message{below > 1 ? "s" : ""}
              </motion.button>
            )}
          </AnimatePresence>
        </div>

        {error && <div className="flex items-center gap-2 px-4 pb-1 text-[12px] text-warn">{error}<button onClick={() => setError(null)} aria-label="Dismiss" className="ml-auto text-faint hover:text-ink"><X size={12} /></button></div>}
        <form data-tour="chat" onSubmit={(e) => { e.preventDefault(); send(); }} className="relative border-t border-line p-3">
          {(mentions.length > 0 || commands.length > 0) && (
            <div className="surface-pop absolute bottom-full left-3 right-3 mb-2 overflow-hidden p-1">
              {mentions.map((n, i) => (
                <button type="button" key={n} onMouseDown={(e) => { e.preventDefault(); pickMention(n); }}
                        className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] ${i === hint % mentions.length ? "bg-elev" : "hover:bg-elev"}`}>
                  {n === "neura1" ? <span className="grid h-6 w-6 place-items-center rounded-full bg-gradient-to-br from-accent to-violet text-white"><Bot size={12} /></span> : <Avatar name={n} size={24} />}
                  {n === "neura1" ? <span><b>neura1</b> <span className="text-muted">· ask the company brain</span></span> : n}
                </button>
              ))}
              {!mentions.length && commands.map(([c, d], i) => (
                <button type="button" key={c} onMouseDown={(e) => { e.preventDefault(); setText(c); box.current?.focus(); }}
                        className={`flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-1.5 text-left ${i === hint % commands.length ? "bg-elev" : "hover:bg-elev"}`}>
                  <span className="font-mono text-[12px]">{c}</span><span className="truncate text-[12px] text-muted">{d}</span>
                </button>
              ))}
            </div>
          )}
          {(reply || editing) && (
            <div className="mb-2 flex items-center gap-2 rounded-xl border-l-2 border-accent bg-elev px-3 py-1.5 text-[12.5px]">
              {editing ? <Pencil size={13} className="shrink-0 text-accent" /> : <CornerUpLeft size={13} className="shrink-0 text-accent" />}
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium">{editing ? "Editing your message" : `Replying to ${reply?.author_id === me ? "yourself" : reply?.author}`}</span>
                {reply && <span className="text-muted"> · {reply.text}</span>}
              </span>
              <button type="button" onClick={() => { setReply(null); if (editing) { setEditing(null); setText(""); } }} aria-label="Cancel" className="text-faint hover:text-ink"><X size={14} /></button>
            </div>
          )}
          <div className="flex items-end gap-2">
            <EmojiButton onPick={(e) => { setText((t) => t + e); box.current?.focus(); }} />
            <textarea ref={box} rows={1} value={text} onChange={(e) => onType(e.target.value)} onKeyDown={onKey}
                      onClick={(e) => onType((e.target as HTMLTextAreaElement).value)} placeholder={placeholder} aria-label="Message"
                      className="max-h-[168px] min-h-[42px] flex-1 resize-none rounded-2xl border border-line px-3.5 py-2.5 text-[14px] leading-snug outline-none focus:border-accent/50" />
            <button disabled={!text.trim()} aria-label={editing ? "Save" : "Send"}
                    className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-full bg-accent text-accent-ink transition hover:bg-accent-hover disabled:opacity-35">
              {editing ? <Check size={18} /> : <SendHorizontal size={18} />}
            </button>
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-3 px-1 text-[11px] text-faint">
            <span className="text-warn/90">Demo workspace: anyone can view as anyone. Don&apos;t post real information.</span>
            <span className="hidden sm:inline">Enter to send · Shift+Enter for a new line · ↑ to edit your last message · Esc to cancel</span>
          </div>
        </form>
      </section>

      {info && conv && (
        <div className="card fixed inset-y-3 right-3 z-40 w-[min(320px,calc(100vw-1.5rem))] overflow-hidden xl:static xl:z-auto xl:w-[300px] xl:shrink-0">
          <InfoPanel key={conv.id + conv.name} c={conv} me={me} people={people} onClose={() => setInfo(false)}
                     onRename={rename} onAdd={addPeople} onRemove={removePerson} />
        </div>
      )}
      {creating && (
        <NewConversation people={people} me={me} busy={busy} error={dialogError} onClose={() => setCreating(false)}
                         onDm={startDm} onGroup={createGroup} onChannel={createChannel} />
      )}
      {evidence && <EvidenceDrawer key={evidence} chunk={evidence} onClose={() => setEvidence(null)} />}
    </div>
  );
}

function EmojiButton({ onPick }: { onPick: (e: string) => void }) {
  const [open, setOpen] = useState(false);
  const more = ["👍", "❤️", "😂", "🎉", "👀", "✅", "🙏", "🔥", "😊", "🤔", "👏", "🚀", "⚠️", "💡", "📌", "☕"];
  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen((x) => !x)} aria-label="Emoji" className="grid h-[42px] w-9 place-items-center rounded-full text-muted hover:bg-elev hover:text-ink"><Smile size={19} /></button>
      {open && (
        <div className="surface-pop absolute bottom-full left-0 z-20 mb-2 grid grid-cols-8 gap-0.5 p-1.5" onMouseLeave={() => setOpen(false)}>
          {more.map((e) => <button type="button" key={e} onClick={() => { onPick(e); setOpen(false); }} className="grid h-8 w-8 place-items-center rounded-lg text-[18px] hover:bg-elev">{e}</button>)}
        </div>
      )}
    </div>
  );
}

function Bubble({ m, me, mine, bot, last, names, flash, people, onReply, onEdit, onDelete, onReact, onJump, onEvidence }: {
  m: Msg; me: string; mine: boolean; bot: boolean; last: boolean; names: string[]; flash: boolean; people: Person[];
  onReply: () => void; onEdit: () => void; onDelete: () => void; onReact: (e: string) => void; onJump: (id: string) => void;
  onEvidence: (chunk: string) => void;
}) {
  const [picker, setPicker] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const links = parseJson<{ label: string; href: string }[]>(m.links, []);
  const sources = parseJson<string[]>(m.sources, []);
  const about = m.about.filter((a) => a.id && !a.id.startsWith("chat/"));
  const nameOf = (id: string) => people.find((p) => p.id === id)?.name ?? id;
  const tone = m.deleted ? "border border-dashed border-line bg-transparent text-muted italic"
    : mine ? "bg-accent text-accent-ink"
    : bot ? "border border-cyan/25 bg-cyan/[0.07] text-ink"
    : "bg-elev-strong text-ink";
  const shape = mine ? `rounded-2xl ${last ? "rounded-br-md" : ""}` : `rounded-2xl ${last ? "rounded-bl-md" : ""}`;

  return (
    <motion.div id={`msg-${m.id}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                className={`group/msg relative mb-0.5 flex w-full flex-col ${mine ? "items-end" : "items-start"}`}
                onMouseLeave={() => { setPicker(false); setConfirm(false); }}>
      <div className={`flex max-w-full items-center gap-1 ${mine ? "flex-row-reverse" : ""}`}>
        <div title={new Date(m.ts).toLocaleString()}
             className={`min-w-0 px-3.5 py-2 text-[14px] leading-relaxed transition-shadow ${tone} ${shape} ${flash ? "ring-2 ring-warn" : ""}`}>
          {m.reply && !m.deleted && (
            <button onClick={() => onJump(m.reply!.id)}
                    className={`mb-1.5 block w-full rounded-lg border-l-2 px-2 py-1 text-left text-[12px] ${mine ? "border-white/60 bg-black/10" : "border-accent bg-black/5 dark:bg-white/5"}`}>
              <span className="block font-semibold">{m.reply.author ?? "Message"}</span>
              <span className="line-clamp-2 opacity-80">{m.reply.deleted ? "Message deleted" : m.reply.text}</span>
            </button>
          )}
          {m.deleted ? <span className="text-[13px]">This message was deleted</span>
            : <span className="whitespace-pre-wrap break-words">{rich(m.text, names, mine)}</span>}
          <span className={`ml-2 inline-flex translate-y-0.5 items-center gap-1 text-[10.5px] ${mine ? "text-accent-ink/70" : "text-faint"}`}>
            {m.edited_at && !m.deleted && "edited ·"} {time(m.ts)}
          </span>
        </div>
        {!m.deleted && m.kind !== "system" && (
          <div className={`flex items-center gap-0.5 rounded-full border border-line bg-panel p-0.5 opacity-0 shadow-sm transition group-hover/msg:opacity-100 focus-within:opacity-100 ${confirm ? "opacity-100" : ""}`}>
            {confirm ? (
              <span className="flex items-center gap-1 px-1.5 text-[11.5px]">
                Delete for everyone?
                <button onClick={() => setConfirm(false)} className="rounded px-1.5 py-0.5 text-muted hover:bg-elev">No</button>
                <button onClick={onDelete} className="rounded bg-danger/15 px-1.5 py-0.5 font-medium text-danger">Delete</button>
              </span>
            ) : (
              <>
                <button onClick={() => setPicker((x) => !x)} aria-label="React" className="rounded-full p-1 text-muted hover:bg-elev hover:text-ink"><Smile size={14} /></button>
                <button onClick={onReply} aria-label="Reply" className="rounded-full p-1 text-muted hover:bg-elev hover:text-ink"><CornerUpLeft size={14} /></button>
                <button onClick={() => navigator.clipboard?.writeText(m.text).catch(() => {})} aria-label="Copy" className="rounded-full p-1 text-muted hover:bg-elev hover:text-ink"><Copy size={13} /></button>
                {mine && m.kind === "message" && <button onClick={onEdit} aria-label="Edit" className="rounded-full p-1 text-muted hover:bg-elev hover:text-ink"><Pencil size={13} /></button>}
                {mine && <button onClick={() => setConfirm(true)} aria-label="Delete" className="rounded-full p-1 text-muted hover:bg-elev hover:text-danger"><Trash2 size={13} /></button>}
              </>
            )}
          </div>
        )}
      </div>
      {picker && (
        <div className={`surface-pop z-20 mt-1 flex gap-0.5 p-1 ${mine ? "mr-1" : "ml-1"}`}>
          {REACTIONS.map((e) => <button key={e} onClick={() => { onReact(e); setPicker(false); }} className="grid h-8 w-8 place-items-center rounded-lg text-[18px] transition hover:scale-110 hover:bg-elev">{e}</button>)}
        </div>
      )}
      {Object.keys(m.reactions).length > 0 && (
        <div className={`mt-1 flex flex-wrap gap-1 ${mine ? "justify-end" : ""}`}>
          {Object.entries(m.reactions).map(([e, who]) => (
            <button key={e} onClick={() => onReact(e)} title={who.map(nameOf).join(", ")}
                    className={`flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[12px] ${who.includes(me) ? "border-accent/50 bg-accent/12" : "border-line bg-panel hover:border-line2"}`}>
              <span>{e}</span><span className="num text-[11px] text-muted">{who.length}</span>
            </button>
          ))}
        </div>
      )}
      {!m.deleted && (links.length > 0 || sources.length > 0) && (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {links.map((l) => <Link key={l.href} href={l.href} className="rounded-md border border-line bg-panel px-2 py-0.5 text-[12px] hover:border-line2">{l.label} →</Link>)}
          {sources.map((s) => <button key={s} onClick={() => onEvidence(s)} className="flex items-center gap-1 rounded-md border border-line bg-panel px-2 py-0.5 text-[12px] hover:border-line2"><FileText size={11} />{s.split("/").pop()}</button>)}
        </div>
      )}
      {!m.deleted && !bot && about.length > 0 && (
        <div className={`mt-1 flex flex-wrap items-center gap-1 text-[11px] text-muted ${mine ? "justify-end" : ""}`}>
          <Link2 size={11} /> linked to
          {about.map((a) => <Link key={a.id} href={(LINK_FOR[a.label] ?? ((x: string) => `/brain?who=${x}`))(a.id)} className="rounded bg-elev px-1.5 py-0.5 text-ink hover:bg-accent/20">{a.label === "Person" ? a.name : a.id}</Link>)}
        </div>
      )}
    </motion.div>
  );
}
