"use client";

import { motion } from "motion/react";
import { Avatar } from "@/components/ViewerSwitch";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Bot, FileText, Hash, Link2, Loader2, MessageCircle, Send, Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import { api, ApiError, viewerId } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";

type Channel = { id: string; name: string; purpose: string | null; kind: "channel" | "dm"; messages: number; last: string | null };
type Msg = { id: string; text: string; author: string; author_id: string | null; ts: string; kind: string;
             sources: string | null; links: string | null; about: { id: string; label: string; name: string }[] };
type Person = { id: string; name: string; team: string };

const COMMANDS = [
  ["/impact NB54360 320 22", "Trace a part change through the company"],
  ["/who CAN bus", "Who knows about something, and why"],
  ["/away Raghavendra", "What changes while someone is away"],
  ["/risk", "Where the company is fragile right now"],
  ["@neura1 ", "Ask the company brain anything, with sources"],
];

const LINK_FOR: Record<string, (id: string) => string> = {
  Person: (id) => `/people?id=${id}`, Project: (id) => `/projects?id=${id}`, Customer: (id) => `/customers?id=${id}`,
  Item: (id) => `/brain?who=${id}`, Revision: (id) => `/brain?who=${id}`, Order: (id) => `/brain?who=${id}`,
  Build: (id) => `/brain?who=${id}`,
};

function rich(text: string) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|@neura1)/gi).map((part, i) =>
    part.startsWith("**") ? <b key={i}>{part.slice(2, -2)}</b>
      : part.startsWith("`") ? <code key={i} className="rounded bg-elev px-1 font-mono text-[12px]">{part.slice(1, -1)}</code>
      : /^@neura1$/i.test(part) ? <span key={i} className="rounded bg-cyan/15 px-1 text-cyan">@neura1</span>
      : <span key={i}>{part}</span>);
}

export default function ChatView() {
  const params = useSearchParams();
  const router = useRouter();
  const current = params.get("c") ?? "chat/general";
  const [channels, setChannels] = useState<Channel[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const me = useMemo(() => viewerId(), []);

  const loadChannels = useCallback(() => api<Channel[]>("/api/chat/channels").then(setChannels).catch(() => {}), []);
  useEffect(() => {
    api<Channel[]>("/api/chat/channels").then(setChannels).catch(() => {});
    api<Person[]>("/api/people").then(setPeople).catch(() => {});
  }, []);

  useEffect(() => {
    let stop = false;
    let last: string | null = null;
    const tick = async () => {
      try {
        const q = `/api/chat/messages?channel=${encodeURIComponent(current)}${last ? `&after=${encodeURIComponent(last)}` : ""}`;
        const fresh = await api<Msg[]>(q);
        if (stop) return;
        if (fresh.length) {
          last = fresh[fresh.length - 1].ts;
          setMsgs((m) => (last && m.length && !q.includes("after") ? fresh : [...m.filter((x) => !fresh.some((f) => f.id === x.id)), ...fresh]));
          if (fresh.some((f) => f.author === "Neura1" && f.kind === "answer")) setWaiting(false);
        }
        setError(null);
      } catch (e) {
        if (!stop) setError((e as Error).message);
      }
    };
    setTimeout(() => setMsgs([]), 0);
    tick();
    const t = setInterval(tick, 2500);
    return () => { stop = true; clearInterval(t); };
  }, [current]);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs.length, waiting]);

  async function send(e?: React.FormEvent) {
    e?.preventDefault();
    const body = text.trim();
    if (!body) return;
    const c = credentials();
    if (!c) return;
    setText("");
    try {
      const r = await api<{ thinking?: boolean }>("/api/chat/messages", { method: "POST", write: true, body: JSON.stringify({ channel: current, text: body }) });
      if (r.thinking) setWaiting(true);
      loadChannels();
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) forgetPasscode();
      setError((err as Error).message);
    }
  }

  async function startDm(personId: string) {
    const r = await api<{ id: string }>("/api/chat/dm", { method: "POST", body: JSON.stringify({ person_id: personId }) });
    await loadChannels();
    router.replace(`/chat?c=${encodeURIComponent(r.id)}`);
  }

  const ch = channels.find((c) => c.id === current);
  const hints = text.startsWith("/") || text === "@" ? COMMANDS.filter(([c]) => c.startsWith(text.split(" ")[0]) || text === "@") : [];

  return (
    <div className="-mb-12 grid h-[calc(100dvh-7rem)] gap-4 lg:grid-cols-[250px_1fr]">
      <aside className="card flex flex-col overflow-hidden">
        <div className="border-b border-line p-4">
          <div className="flex items-center gap-2 font-medium"><MessageCircle size={16} className="text-cyan" /> Neura1 Chat</div>
          <p className="mt-1 text-xs text-muted">Every message here becomes company knowledge instantly.</p>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          <div className="px-2 pb-1 pt-2 text-[10.5px] uppercase tracking-[0.12em] text-muted">Channels</div>
          {channels.filter((c) => c.kind === "channel").map((c) => (
            <button key={c.id} onClick={() => router.replace(`/chat?c=${encodeURIComponent(c.id)}`)}
                    className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${c.id === current ? "bg-accent/15 text-ink" : "text-muted hover:bg-elev hover:text-ink"}`}>
              <Hash size={14} />{c.name}{c.messages > 0 && <span className="ml-auto text-[10px] tabular-nums">{c.messages}</span>}
            </button>
          ))}
          <div className="px-2 pb-1 pt-4 text-[10.5px] uppercase tracking-[0.12em] text-muted">Direct messages</div>
          {channels.filter((c) => c.kind === "dm").map((c) => (
            <button key={c.id} onClick={() => router.replace(`/chat?c=${encodeURIComponent(c.id)}`)}
                    className={`block w-full truncate rounded-lg px-2 py-1.5 text-left text-sm ${c.id === current ? "bg-accent/15 text-ink" : "text-muted hover:bg-elev hover:text-ink"}`}>{c.name}</button>
          ))}
          <select value="" onChange={(e) => e.target.value && startDm(e.target.value)} className="mt-1 w-full rounded-lg border border-line px-2 py-1.5 text-xs text-muted">
            <option value="">+ Message someone…</option>
            {people.filter((p) => p.id !== me).map((p) => <option key={p.id} value={p.id}>{p.name} · {p.team}</option>)}
          </select>
        </div>
      </aside>

      <section className="card flex min-h-0 flex-col">
        <header className="flex items-center gap-2 border-b border-line px-5 py-3">
          {ch?.kind === "dm" ? <MessageCircle size={16} className="text-muted" /> : <Hash size={16} className="text-muted" />}
          <span className="font-medium">{ch?.name ?? current.replace("chat/", "")}</span>
          <span className="truncate text-xs text-muted">{ch?.purpose}</span>
          <span className="ml-auto flex items-center gap-1 text-[11px] text-muted"><Sparkles size={12} className="text-cyan" /> @neura1 is in every channel</span>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {!msgs.length && <div className="grid h-full place-items-center text-sm text-muted">No messages yet. Say hello, try a command, or ask @neura1.</div>}
          {msgs.map((m) => {
            const bot = m.author === "Neura1";
            const links: { label: string; href: string }[] = m.links ? JSON.parse(m.links) : [];
            const sources: string[] = m.sources ? JSON.parse(m.sources) : [];
            const about = m.about.filter((a) => a.id && !a.id.startsWith("chat/"));
            return (
              <motion.div key={m.id} className="flex gap-3" initial={{ opacity: 0, y: 10, filter: "blur(4px)" }}
                          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}>
                {bot
                  ? <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-accent to-violet text-white"><Bot size={15} /></span>
                  : <Avatar name={m.author} size={32} />}
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2 text-sm">
                    {m.author_id ? <Link href={`/people?id=${m.author_id}`} className="font-medium hover:underline">{m.author}</Link> : <span className="font-medium text-cyan">{m.author}</span>}
                    <span className="text-[11px] text-muted">{new Date(m.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                    {bot && m.kind === "notice" && <span className="rounded bg-violet/15 px-1.5 text-[10px] text-violet">posted on its own</span>}
                  </div>
                  <div className={`mt-0.5 whitespace-pre-wrap text-sm leading-relaxed ${bot ? "rounded-xl border border-cyan/25 bg-cyan/[0.07] px-3 py-2" : ""}`}>{rich(m.text)}</div>
                  {(links.length > 0 || sources.length > 0) && (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {links.map((l) => <Link key={l.href} href={l.href} className="rounded-md border border-line px-2 py-0.5 text-xs hover:border-line2">{l.label} →</Link>)}
                      {sources.map((s) => <button key={s} onClick={() => setOpen(s)} className="flex items-center gap-1 rounded-md border border-line px-2 py-0.5 text-xs hover:border-line2"><FileText size={11} />{s.split("/").pop()}</button>)}
                    </div>
                  )}
                  {!bot && about.length > 0 && (
                    <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-muted">
                      <Link2 size={11} /> linked to
                      {about.map((a) => <Link key={a.id} href={(LINK_FOR[a.label] ?? ((x: string) => `/brain?who=${x}`))(a.id)} className="rounded bg-elev px-1.5 py-0.5 text-ink hover:bg-accent/20">{a.label === "Person" ? a.name : a.id}</Link>)}
                    </div>
                  )}
                </div>
              </motion.div>
            );
          })}
          {waiting && <div className="flex items-center gap-2 pl-11 text-xs text-muted"><Loader2 size={13} className="animate-spin" /> Neura1 is working through the graph…</div>}
          <div ref={bottom} />
        </div>
        {error && <div className="px-5 pb-1 text-xs text-warn">{error}</div>}
        <form onSubmit={send} className="relative border-t border-line p-3">
          {hints.length > 0 && (
            <div className="absolute bottom-full left-3 right-3 mb-2 overflow-hidden rounded-xl border border-line bg-panel backdrop-blur">
              {hints.map(([c, d]) => (
                <button type="button" key={c} onClick={() => setText(c)} className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-elev">
                  <span className="font-mono text-xs">{c}</span><span className="text-xs text-muted">{d}</span>
                </button>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder={`Message ${ch?.kind === "dm" ? ch.name : "#" + (ch?.name ?? "general")} · type / for commands or @neura1 to ask`}
                   className="flex-1 rounded-xl border border-line px-3 py-2.5 text-sm" />
            <button className="flex items-center gap-1.5 rounded-xl bg-accent px-4 text-sm text-white hover:bg-accent-hover"><Send size={14} /> Send</button>
          </div>
        </form>
      </section>
      {open && <EvidenceDrawer key={open} chunk={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
