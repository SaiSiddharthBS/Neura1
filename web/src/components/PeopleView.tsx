"use client";

import { PageTitle } from "@/components/ui";
import { Avatar } from "@/components/ViewerSwitch";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CalendarOff, CheckCircle2, ChevronRight, CircleDot, Lock, Pencil, Search, UserPlus } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import PlanPanel, { type PlanAction, type PlanInvestigation } from "@/components/PlanPanel";
import { api, ApiError, plain } from "@/lib/api";
import { credentials, forgetPasscode } from "@/lib/session";

type Row = { id: string; name: string; role: string; team: string };
type Work = { id: string; title: string; status: string; kind: string; created_at: string; completed_at: string | null;
              project: string | null; project_id: string | null; investigation: string | null; plan_kind: string | null };
type Absence = { start_date: string; end_date: string; kind: string; note: string | null };
type Person = {
  id: string; name: string; role: string; team: string; team_id: string; organization: string | null;
  manager: string | null; manager_id: string | null;
  reports: { id: string; name: string; role: string }[];
  backed_up_by: { id: string; name: string }[]; backs_up: { id: string; name: string }[];
  org_roles: { role: string; org: string }[];
  reporting_chain: { id: string; name: string; role: string }[];
  skills: { id: string; name: string; also: string[] }[];
  work: { current: Work[]; finished: Work[]; counts: Record<string, number> };
  leave: { away_now: boolean; restricted?: boolean; current?: Absence | null; upcoming?: Absence[]; past?: Absence[] };
  projects: { id: string; name: string; status: string; roles: string[] }[];
  owns: { id: string; label: string; name: string }[];
  decisions: { id: string; outcome: string; subject: string; decided_at: string }[];
  topics: { id: string; label: string; mentions: number }[];
  recent: { chunk: string; text: string; ts: string; title: string }[];
};
type AwayPlan = {
  status: string; absence: { start: string | null; end: string | null };
  knowledge_at_risk: { id: string; share: number; next_best: string | null }[];
  conflicts: string[]; actions: PlanAction[]; investigation: PlanInvestigation;
};

const STATUS: Record<string, string> = { open: "text-muted", in_progress: "text-accent-hover", blocked: "text-danger", done: "text-success" };


export default function PeopleView() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const [people, setPeople] = useState<Row[]>([]);
  const [q, setQ] = useState("");
  const [p, setP] = useState<Person | null>(null);
  const [away, setAway] = useState<AwayPlan | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);

  const loadPerson = useCallback(() => {
    if (!id) return;
    api<Person>(`/api/people/${id}`).then(setP);
    api<AwayPlan>(`/api/scenarios/absence/${id}`).then(setAway).catch(() => setAway(null));
  }, [id]);
  useEffect(() => { api<Row[]>("/api/people").then(setPeople); }, []);
  useEffect(() => { loadPerson(); }, [loadPerson]);

  const groups = useMemo(() => {
    const m = new Map<string, Row[]>();
    people.filter((r) => !q || `${r.name} ${r.role} ${r.team}`.toLowerCase().includes(q.toLowerCase()))
      .forEach((r) => m.set(r.team, [...(m.get(r.team) ?? []), r]));
    return [...m.entries()].sort(([a], [b]) => (a === "Board" ? 1 : b === "Board" ? -1 : a.localeCompare(b)));
  }, [people, q]);

  return (
    <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
      <aside className="card h-fit">
        <div className="flex items-center gap-2 border-b border-line p-3">
          <Search size={14} className="text-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${people.length} people`}
                 className="flex-1 bg-transparent text-sm outline-none" style={{ background: "transparent" }} />
          <button onClick={() => setAdding(true)} title="Add a person" className="rounded-md p-1 text-muted hover:text-ink"><UserPlus size={15} /></button>
        </div>
        <div className="max-h-[75vh] overflow-y-auto">
          {groups.map(([team, rows]) => (
            <div key={team}>
              <div className="sticky top-0 bg-panel px-4 pb-1 pt-3 text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted backdrop-blur">{team}</div>
              {rows.map((r) => (
                <button key={r.id} onClick={() => router.replace(`/people?id=${r.id}`)}
                        className={`flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-elev ${r.id === id ? "bg-accent/15" : ""}`}>
                  <Avatar name={r.name} size={28} />
                  <span className="min-w-0"><span className="block truncate text-sm font-medium">{r.name}</span><span className="block truncate text-xs text-muted">{r.role}</span></span>
                </button>
              ))}
            </div>
          ))}
        </div>
      </aside>

      {!id || !p ? (
        <div className="card p-8 text-sm text-muted">Pick a person to see what they own, what they are working on, what they have finished, their leave, their skills and who they work with.</div>
      ) : (
        <section className="space-y-4">
          <div className="card p-5">
            <div className="flex flex-wrap items-start gap-4">
              <Avatar name={p.name} size={56} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <PageTitle key={p.id}>{p.name}</PageTitle>
                  {p.leave.away_now
                    ? <span className="rounded-full bg-warn/15 px-2 py-0.5 text-xs text-warn">Away today</span>
                    : <span className="rounded-full bg-success/15 px-2 py-0.5 text-xs text-success">Available</span>}
                </div>
                <div className="text-sm text-muted">{p.role} · {p.team}{p.organization ? ` · ${p.organization}` : ""}</div>
                <div className="mt-2 flex flex-wrap items-center gap-1 text-xs text-muted">
                  {[...p.reporting_chain].reverse().map((c) => (
                    <span key={c.id} className="flex items-center gap-1"><Link href={`/people?id=${c.id}`} className="hover:text-ink">{c.name}</Link><ChevronRight size={12} /></span>
                  ))}
                  <span className="text-ink">{p.name}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                  {p.org_roles.map((r) => <span key={r.role + r.org} className="rounded-full bg-violet/15 px-2 py-0.5 text-violet">{r.role}, {r.org}</span>)}
                  {p.backed_up_by.map((b) => <span key={b.id} className="rounded-full bg-elev px-2 py-0.5">When away: {b.name}</span>)}
                  {p.backs_up.length > 0 && <span className="rounded-full bg-elev px-2 py-0.5">Covers for {p.backs_up.map((b) => b.name).join(", ")}</span>}
                  {p.reports.length > 0 && <span className="rounded-full bg-elev px-2 py-0.5">{p.reports.length} direct reports</span>}
                </div>
              </div>
              <button onClick={() => setEditing(true)} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm hover:border-line2"><Pencil size={13} /> Edit</button>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
              {[["In progress", p.work.counts.in_progress, "text-accent-hover"], ["To do", p.work.counts.open, "text-ink"],
                ["Blocked", p.work.counts.blocked, "text-danger"], ["Finished", p.work.counts.done, "text-success"]].map(([l, n, c]) => (
                <div key={l as string} className="rounded-xl bg-elev px-3 py-2"><div className={`text-xl font-semibold tabular-nums ${c}`}>{n}</div><div className="text-[11px] text-muted">{l}</div></div>
              ))}
            </div>
          </div>

          {away?.status === "ok" && away.absence.start && (
            <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
              <div className="card space-y-3 border-warn/40 p-5">
                <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-warn"><CalendarOff size={13} /> Away {away.absence.start} → {away.absence.end}</div>
                {away.conflicts.map((c) => <div key={c} className="rounded-lg bg-warn/10 px-3 py-1.5 text-sm text-warn">{c}</div>)}
                <div className="text-xs text-muted">Knowledge the company relies on {p.name} for</div>
                {away.knowledge_at_risk.map((k) => (
                  <div key={k.id} className="flex items-center gap-3 text-sm">
                    <span className="w-28 font-mono text-xs">{k.id}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-elev"><div className="h-full bg-warn" style={{ width: `${k.share * 100}%` }} /></div>
                    <span className="text-xs text-muted">next best: {k.next_best ?? "nobody"}</span>
                  </div>
                ))}
                {!away.knowledge_at_risk.length && <div className="text-sm text-muted">Nothing where {p.name} is the main source.</div>}
              </div>
              <PlanPanel title="Handover plan (HB-HR-02)" kind="absence" subject={p.id} actions={away.actions} investigation={away.investigation} onDone={loadPerson} />
            </div>
          )}

          <div className="grid gap-4 xl:grid-cols-2">
            <Card title="Working on now">
              {p.work.current.map((w) => <WorkRow key={w.id} w={w} />)}
              {!p.work.current.length && <Empty />}
            </Card>
            <Card title="Finished">
              {p.work.finished.map((w) => <WorkRow key={w.id} w={w} />)}
              {!p.work.finished.length && <Empty />}
            </Card>
            <Card title="Leave">
              {p.leave.restricted ? (
                <div className="flex items-center gap-2 text-sm text-muted"><Lock size={13} /> Leave dates are visible to {p.name}, their management chain, their backup, HR and leadership.</div>
              ) : (
                <div className="space-y-1.5 text-sm">
                  {p.leave.current && <div className="text-warn">Away now until {p.leave.current.end_date}</div>}
                  {p.leave.upcoming?.map((a) => <div key={a.start_date}>{a.start_date} → {a.end_date} <span className="text-xs text-muted">· {a.kind}</span></div>)}
                  {p.leave.past?.map((a) => <div key={a.start_date} className="text-muted">{a.start_date} → {a.end_date} (past)</div>)}
                  {!p.leave.current && !p.leave.upcoming?.length && !p.leave.past?.length && <Empty text="No leave recorded." />}
                </div>
              )}
            </Card>
            <Card title="Skills (stated) and knowledge (from their work)">
              <div className="flex flex-wrap gap-1.5">
                {p.skills.map((s) => <span key={s.id} title={s.also.length ? `Also: ${s.also.join(", ")}` : "Only person with this skill"}
                                          className={`rounded-full px-2 py-0.5 text-xs ${s.also.length ? "bg-accent/15 text-accent-hover" : "bg-warn/15 text-warn"}`}>{s.name}</span>)}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {p.topics.map((t) => <span key={t.id} className="rounded-md bg-elev px-2 py-0.5 font-mono text-xs">{t.id} · {t.mentions}×</span>)}
              </div>
              {!p.skills.length && !p.topics.length && <Empty />}
            </Card>
            <Card title="Projects">
              {p.projects.map((x) => <Link key={x.id} href={`/projects?id=${x.id}`} className="block rounded-lg px-2 py-1 text-sm hover:bg-elev">{x.name} <span className="text-xs text-muted">· {x.roles.join(", ")} · {x.status}</span></Link>)}
              {!p.projects.length && <Empty />}
            </Card>
            <Card title="Owns and decided">
              <div className="flex flex-wrap gap-1.5">{p.owns.map((o) => <span key={o.id} className="rounded-md bg-elev px-2 py-0.5 font-mono text-xs">{o.id} · {o.label}</span>)}</div>
              {p.decisions.map((d) => <div key={d.id} className="mt-2 text-sm"><b>{d.id}</b> {d.outcome} {d.subject} <span className="text-xs text-muted">· {d.decided_at}</span></div>)}
              {!p.owns.length && !p.decisions.length && <Empty />}
            </Card>
            {p.reports.length > 0 && (
              <Card title="Team">
                {p.reports.map((r) => <Link key={r.id} href={`/people?id=${r.id}`} className="block rounded-lg px-2 py-1 text-sm hover:bg-elev">{r.name} <span className="text-xs text-muted">· {r.role}</span></Link>)}
              </Card>
            )}
            <Card title="Recently said">
              {p.recent.map((r) => (
                <button key={r.chunk} onClick={() => setOpen(r.chunk)} className="block w-full rounded-lg px-2 py-1.5 text-left text-sm hover:bg-elev">
                  <span className="text-xs text-muted">{r.title} · {r.ts?.slice(0, 10)}</span><div className="line-clamp-2">{plain(r.text)}</div>
                </button>
              ))}
              {!p.recent.length && <Empty />}
            </Card>
          </div>
        </section>
      )}
      {editing && p && <EditPerson p={p} people={people} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); loadPerson(); api<Row[]>("/api/people").then(setPeople); }} />}
      {adding && <AddPerson onClose={() => setAdding(false)} onSaved={(nid) => { setAdding(false); api<Row[]>("/api/people").then(setPeople); router.replace(`/people?id=${nid}`); }} />}
      {open && <EvidenceDrawer key={open} chunk={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function WorkRow({ w }: { w: Work }) {
  const Icon = w.status === "done" ? CheckCircle2 : CircleDot;
  return (
    <div className="flex items-start gap-2 py-1.5 text-sm">
      <Icon size={14} className={`mt-0.5 shrink-0 ${STATUS[w.status]}`} />
      <div className="min-w-0 flex-1">
        <div className="leading-snug">{w.title}</div>
        <div className="text-xs text-muted">
          {w.project ?? (w.plan_kind ? `${w.plan_kind.replace("_", " ")} plan` : "")}
          {w.status === "done" && w.completed_at ? ` · finished ${w.completed_at}` : ` · ${w.status.replace("_", " ")} · since ${w.created_at?.slice(0, 10)}`}
        </div>
      </div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="card p-4"><div className="mb-2 text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted">{title}</div>{children}</div>;
}
function Empty({ text = "Nothing recorded." }: { text?: string }) { return <span className="text-sm text-muted">{text}</span>; }

type Team = { id: string; name: string };

function useTeams() {
  const [teams, setTeams] = useState<Team[]>([]);
  useEffect(() => { api<Team[]>("/api/teams").then(setTeams); }, []);
  return teams;
}

function EditPerson({ p, people, onClose, onSaved }: { p: Person; people: Row[]; onClose: () => void; onSaved: () => void }) {
  const teams = useTeams();
  const [role, setRole] = useState(p.role);
  const [team, setTeam] = useState(p.team_id);
  const [manager, setManager] = useState(p.manager_id ?? "");
  const [backup, setBackup] = useState(p.backed_up_by[0]?.id ?? "");
  const [skill, setSkill] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  async function save() {
    const c = credentials();
    if (!c) return;
    const body: Record<string, unknown> = { by: c.name };
    if (role !== p.role) body.role = role;
    if (team !== p.team_id) body.team_id = team;
    if (manager && manager !== p.manager_id) body.manager_id = manager;
    if (backup && backup !== p.backed_up_by[0]?.id) body.backup_id = backup;
    if (skill.trim()) body.add_skills = skill.split(",").map((x) => x.trim()).filter(Boolean);
    if (from && to) body.absence = { start_date: from, end_date: to, kind: "planned leave" };
    try {
      await api(`/api/people/${p.id}`, { method: "PATCH", write: true, body: JSON.stringify(body) });
      onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) forgetPasscode();
      setMsg((e as Error).message);
    }
  }
  const others = people.filter((x) => x.id !== p.id);
  return (
    <Drawer title={`Edit ${p.name}`} onClose={onClose}>
      <Field label="Role"><input value={role} onChange={(e) => setRole(e.target.value)} className="w-full rounded-md border border-line px-2 py-1.5" /></Field>
      <Field label="Team"><select value={team} onChange={(e) => setTeam(e.target.value)} className="w-full rounded-md border border-line px-2 py-1.5">{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
      <Field label="Reports to"><select value={manager} onChange={(e) => setManager(e.target.value)} className="w-full rounded-md border border-line px-2 py-1.5"><option value="">—</option>{others.map((o) => <option key={o.id} value={o.id}>{o.name} · {o.role}</option>)}</select></Field>
      <Field label="Backup when away"><select value={backup} onChange={(e) => setBackup(e.target.value)} className="w-full rounded-md border border-line px-2 py-1.5"><option value="">—</option>{others.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></Field>
      <Field label="Add skills (comma separated)"><input value={skill} onChange={(e) => setSkill(e.target.value)} placeholder="e.g. MIL-STD-461 testing" className="w-full rounded-md border border-line px-2 py-1.5" /></Field>
      <Field label="Add planned leave">
        <div className="flex gap-2"><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="flex-1 rounded-md border border-line px-2 py-1.5" /><input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="flex-1 rounded-md border border-line px-2 py-1.5" /></div>
      </Field>
      <button onClick={save} className="w-full rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-accent-hover">Save to the graph</button>
      <p className="text-xs text-muted">Every change is stored as an event with who made it, and shows in What&apos;s new.</p>
      {msg && <p className="text-sm text-danger">{msg}</p>}
    </Drawer>
  );
}

function AddPerson({ onClose, onSaved }: { onClose: () => void; onSaved: (id: string) => void }) {
  const teams = useTeams();
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [team, setTeam] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  async function save() {
    const c = credentials();
    if (!c || !name.trim()) return;
    const id = "P-" + name.trim().toUpperCase().replace(/[^A-Z0-9]+/g, "-");
    try {
      await api("/api/people", { method: "POST", write: true, body: JSON.stringify({ id, name: name.trim(), role: role.trim() || "Employee", team_id: team || null, by: c.name }) });
      onSaved(id);
    } catch (e) { setMsg((e as Error).message); }
  }
  return (
    <Drawer title="Add a person" onClose={onClose}>
      <Field label="Name"><input value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-md border border-line px-2 py-1.5" /></Field>
      <Field label="Role"><input value={role} onChange={(e) => setRole(e.target.value)} className="w-full rounded-md border border-line px-2 py-1.5" /></Field>
      <Field label="Team"><select value={team} onChange={(e) => setTeam(e.target.value)} className="w-full rounded-md border border-line px-2 py-1.5"><option value="">—</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
      <button onClick={save} className="w-full rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-accent-hover">Add</button>
      {msg && <p className="text-sm text-danger">{msg}</p>}
    </Drawer>
  );
}

function Drawer({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <aside className="card h-full w-full max-w-md space-y-4 overflow-y-auto rounded-none p-5" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold">{title}</h2>
        {children}
      </aside>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block text-sm"><span className="mb-1 block text-xs text-muted">{label}</span>{children}</label>;
}
