"use client";

import Link from "next/link";
import { CalendarOff, CheckCircle2, CircleDot, Newspaper, Radio, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import BriefCard from "@/components/BriefCard";
import { PageTitle } from "@/components/ui";
import { api, plain } from "@/lib/api";

type Work = { id: string; title: string; status: string; project: string | null; kind: string; created_at: string; completed_at: string | null };
type Me = {
  status: string;
  me: { name: string; role: string; team: string; manager: string | null; work: { current: Work[]; finished: Work[] };
        leave: { away_now: boolean; upcoming?: { start_date: string; end_date: string }[] } };
  news: { chunk: string; title: string; kind: string; author: string | null; ts: string; text: string; about: string[] }[];
  signals: { id: string; kind: string; title: string; subject: string }[];
  team_away: { id: string; name: string; start_date: string; end_date: string }[];
  approvals: Work[];
};

export default function MyDay() {
  const [d, setD] = useState<Me | null>(null);
  useEffect(() => { api<Me>("/api/me").then(setD); }, []);
  if (!d) return <div className="p-6 text-muted">Preparing your day…</div>;
  if (d.status !== "ok") return <div className="card p-6 text-muted">Choose who you are in “Viewing as” to see your day.</div>;
  const m = d.me;
  const today = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-1.5 text-[13px] text-muted"><Sun size={13} /> {today}</div>
        <PageTitle className="mt-1">{"Your day,"} <em>{m.name}</em></PageTitle>
        <p className="mt-1.5 text-[15px] text-muted">{m.role}. What changed in your areas, what is waiting for you, and who is away.</p>
      </div>
      <BriefCard />
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <section className="card p-5">
          <div className="flex items-center justify-between font-medium"><span>Your work</span><Link href="/board" className="text-xs text-muted hover:text-ink">Workboard →</Link></div>
          {d.approvals.length > 0 && (
            <div className="mt-3 rounded-xl border border-accent/25 bg-accent/[0.07] p-3 text-sm">
              <div className="mb-1 text-xs uppercase tracking-wide text-accent-hover">Needs your decision</div>
              {d.approvals.map((w) => <div key={w.id}>{w.title}</div>)}
            </div>
          )}
          <div className="mt-3 space-y-1.5">
            {m.work.current.map((w) => (
              <div key={w.id} className="flex items-start gap-2 text-sm"><CircleDot size={14} className={`mt-0.5 ${w.status === "blocked" ? "text-danger" : w.status === "in_progress" ? "text-accent-hover" : "text-muted"}`} />
                <span className="flex-1">{w.title}<span className="block text-xs text-muted">{w.project ?? w.kind} · {w.status.replace("_", " ")}</span></span></div>
            ))}
            {!m.work.current.length && <div className="text-sm text-muted">Nothing open. </div>}
          </div>
          {m.work.finished.length > 0 && (
            <div className="mt-4 border-t border-line pt-3 text-xs text-muted">
              Recently finished: {m.work.finished.slice(0, 3).map((w) => <span key={w.id} className="mr-2 inline-flex items-center gap-1"><CheckCircle2 size={12} className="text-success" />{w.title}</span>)}
            </div>
          )}
        </section>
        <div className="space-y-4">
          <section className="card p-5">
            <div className="flex items-center gap-2 font-medium"><Radio size={15} className="text-warn" /> Signals touching your areas</div>
            <div className="mt-2 space-y-1.5 text-sm">
              {d.signals.map((s) => <div key={s.id}>{s.title} <span className="text-xs text-muted">· {s.kind}</span></div>)}
              {!d.signals.length && <div className="text-muted">None right now.</div>}
            </div>
          </section>
          <section className="card p-5">
            <div className="flex items-center gap-2 font-medium"><CalendarOff size={15} className="text-accent-hover" /> Away in your team</div>
            <div className="mt-2 space-y-1 text-sm">
              {d.team_away.map((a) => <Link key={a.id + a.start_date} href={`/people?id=${a.id}`} className="block hover:underline">{a.name} <span className="text-xs text-muted">{a.start_date} → {a.end_date}</span></Link>)}
              {!d.team_away.length && <div className="text-muted">Everyone is in.</div>}
              {m.leave.upcoming?.map((a) => <div key={a.start_date} className="text-warn">You: {a.start_date} → {a.end_date}</div>)}
            </div>
          </section>
        </div>
      </div>
      <section className="card p-5">
        <div className="flex items-center gap-2 font-medium"><Newspaper size={15} className="text-accent-hover" /> What changed in things you own or work on (last 45 days)</div>
        <div className="mt-3 divide-y divide-line">
          {d.news.map((n) => (
            <div key={n.chunk} className="py-2 text-sm"><span className="text-xs text-muted">{n.ts?.slice(0, 10)} · {n.title}{n.author ? ` · ${n.author}` : ""} · about {n.about.join(", ")}</span><div className="line-clamp-2">{plain(n.text)}</div></div>
          ))}
          {!d.news.length && <div className="text-sm text-muted">Quiet.</div>}
        </div>
      </section>
    </div>
  );
}
