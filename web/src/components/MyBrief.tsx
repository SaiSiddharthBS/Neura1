"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { Bot, Loader2, MessageCircle, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";

type Brief = { date: string; text: string; links: { label: string; href: string }[] };

function bold(line: string) {
  return line.split(/(\*\*[^*]+\*\*)/).map((p, i) => (p.startsWith("**") && p.endsWith("**") ? <b key={i}>{p.slice(2, -2)}</b> : <span key={i}>{p}</span>));
}

/** This person's own brief, the same one Neura1 posts in their private chat at 09:00. */
export default function MyBrief() {
  const [b, setB] = useState<Brief | null>(null);
  const [busy, setBusy] = useState(false);
  const [channel, setChannel] = useState<string | null>(null);
  useEffect(() => { api<Brief | null>("/api/brief/me").then(setB).catch(() => {}); }, []);
  if (!b) return null;
  const [greeting, ...rest] = b.text.split("\n");
  const lines = rest.filter((l) => l.startsWith("•"));

  async function send() {
    if (!credentials()) return;
    setBusy(true);
    try {
      const r = await api<{ channel: string }>("/api/brief/me", { method: "POST", write: true });
      setChannel(r.channel);
      toast.success("Sent to your Neura1 chat");
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) forgetPasscode();
      toast.error((e as Error).message);
    } finally { setBusy(false); }
  }

  return (
    <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                    className="relative overflow-hidden rounded-[22px] border border-accent/25 bg-gradient-to-br from-accent/[0.09] via-violet/[0.05] to-transparent p-5">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-gradient-to-br from-accent to-violet text-white shadow-[0_0_24px_-6px_var(--accent)]"><Bot size={18} /></span>
        <div className="min-w-0 flex-1">
          <div className="text-[12px] font-semibold uppercase tracking-[0.08em] text-accent">Your brief from Neura1</div>
          <div className="mt-0.5 text-[15.5px] font-semibold">{greeting}</div>
          <ul className="mt-2 space-y-1.5">
            {lines.map((l, i) => (
              <motion.li key={l} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 + i * 0.06 }} className="text-[13.5px] leading-relaxed text-ink-soft">{bold(l)}</motion.li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {b.links.filter((l) => l.href !== "/me").map((l) => <Link key={l.href} href={l.href} className="rounded-lg border border-line bg-panel px-2.5 py-1 text-[12px] hover:border-line2">{l.label} →</Link>)}
            {channel
              ? <Link href={`/chat?c=${encodeURIComponent(channel)}`} className="ml-auto flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-[12.5px] font-medium text-accent-ink hover:bg-accent-hover"><MessageCircle size={13} /> Open the chat</Link>
              : <button onClick={send} disabled={busy} className="press ml-auto flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-[12.5px] font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-50">
                  {busy ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Send to my Neura1 chat</button>}
          </div>
        </div>
      </div>
    </motion.section>
  );
}
