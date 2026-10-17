"use client";

import Link from "next/link";
import { Coffee } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Today's company brief, the same one Neura1 posts to #general at 09:00 IST. */
export default function BriefCard() {
  const [b, setB] = useState<{ date: string; text: string } | null>(null);
  useEffect(() => { api<{ date: string; text: string }>("/api/brief").then(setB).catch(() => {}); }, []);
  if (!b) return null;
  const [first, ...rest] = b.text.split("\n");
  return (
    <section className="card p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[14px] font-semibold tracking-tight"><Coffee size={15} className="text-warn" /> This morning&apos;s brief</div>
        <Link href="/chat" className="text-[12.5px] text-muted hover:text-ink">Posted in #general at 09:00 →</Link>
      </div>
      <p className="mt-2 text-[13.5px] text-ink-soft">{first}</p>
      <ul className="mt-2 space-y-1.5 text-[13.5px]">
        {rest.map((l, i) => <li key={i} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" /><span>{l.replace(/^•\s*/, "")}</span></li>)}
      </ul>
    </section>
  );
}
