"use client";

import { AnimatePresence, motion } from "motion/react";
import {
  ArrowRight, Bot, CheckCircle2, Copy, Database, Eye, EyeOff, GitCompareArrows, Loader2, Lock, MessageSquare, Plug,
  PlugZap, RefreshCw, ShieldCheck, Sparkles, XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageTitle, Pill } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Change = { kind: string; id: string; change: "new" | "updated"; fields: Record<string, [string, string]>; summary: string };
type Run = { id: string; at: string; by: string | null; simulated: boolean; changes: number; changes_list: Change[] };
type Connect = {
  source: { id: string; title: string; transport: string; simulated: boolean; endpoint: string; reads: string[]; schedule_minutes: number };
  runs: Run[]; can_sync: boolean;
};
type Report = {
  ok: boolean; dry_run?: boolean; at?: string; tools?: string[]; read?: Record<string, number>; warnings?: string[];
  changes?: Change[]; message?: string; run?: string; error?: string; stage?: string;
};
type Agents = {
  mcp: { enabled: boolean; path: string; transport: string; read_as: string; sees_money: boolean; sees_leave: boolean;
         tools: { name: string; description: string }[] };
  alerts: { enabled: boolean };
};

const KIND_LABEL: Record<string, string> = {
  stock: "Stock", purchase_orders: "Purchase order", receipts: "Goods received", stock_moves: "Stock movement",
  projects: "Project", tasks: "Task",
};
const READ_LABEL: Record<string, string> = {
  stock: "stock levels", purchase_orders: "purchase orders", receipts: "goods received", projects: "projects", tasks: "tasks",
};
const when = (s: string) => new Date(s).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function err(e: unknown) {
  return e instanceof ApiError ? String((e.body as { detail?: unknown })?.detail ?? e.message) : (e as Error).message;
}

export default function ConnectPage() {
  const [c, setC] = useState<Connect | null>(null);
  const [agents, setAgents] = useState<Agents | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [preview, setPreview] = useState<Report | null>(null);
  const [probe, setProbe] = useState<{ ok: boolean; tools?: { name: string; description: string }[]; error?: string } | null>(null);
  const [agentTest, setAgentTest] = useState<{ ok: boolean; tools?: string[]; sample?: { summary: { late: number; projects_late: number }; read_as: string }; error?: string } | null>(null);
  const [alert, setAlert] = useState<{ text: string; sent: boolean; reason?: string } | null>(null);

  const load = () => {
    api<Connect>("/api/connect").then(setC).catch(() => {});
    api<Agents>("/api/agents").then(setAgents).catch(() => {});
  };
  useEffect(load, []);

  async function go<T>(key: string, path: string, body?: unknown): Promise<T | null> {
    setBusy(key);
    try {
      return await api<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });
    } catch (e) {
      toast.error(err(e));
      return null;
    } finally { setBusy(null); }
  }

  async function sync(dry: boolean) {
    const r = await go<Report>(dry ? "preview" : "sync", "/api/connect/zoho/sync", { dry_run: dry });
    if (!r) return;
    if (!r.ok) { toast.error(r.error ?? "The sync did not complete"); setPreview(r); return; }
    setPreview(r);
    if (!dry) {
      toast.success(r.message ?? "Synced", { description: r.changes?.length ? "The timeline, inventory and What's new are updated." : undefined });
      load();
    }
  }

  const canSync = c?.can_sync ?? false;
  const btn = "press flex items-center gap-2 rounded-full px-4 py-2 text-[13px] font-medium transition disabled:opacity-40";

  return (
    <div className="space-y-6">
      <div>
        <PageTitle>Works with the systems you <em>already</em> plan in</PageTitle>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Neura1 is an add-on, not a replacement on day one. It reads the ERP and the project planner over the Model Context
          Protocol, keeps the company graph in step with them, and lets the agents your team works with ask it questions.
          Nothing is exported by hand, and every sync shows exactly what changed.
        </p>
      </div>

      <Flow />

      <div className="grid gap-5 xl:grid-cols-2">
        {/* ERP and planner */}
        <section className="card flex flex-col p-5">
          <header className="flex flex-wrap items-start gap-3">
            <span className="rounded-xl bg-accent/12 p-2.5 text-accent"><Database size={18} /></span>
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-semibold tracking-tight">{c?.source.title ?? "Zoho Inventory + Zoho Projects"}</div>
              <div className="mt-0.5 text-[12.5px] text-muted">ERP and project planner · MCP over {c?.source.transport ?? "…"}</div>
            </div>
            {c && (c.source.simulated ? <Pill tone="warn" dot>Simulated Zoho (demo)</Pill> : <Pill tone="success" dot>Live</Pill>)}
          </header>
          {c?.source.simulated && (
            <p className="mt-3 rounded-xl border border-line bg-elev px-3 py-2 text-[12.5px] text-muted">
              The demo reads a simulated Zoho that serves the synthetic Flyvi records in Zoho&apos;s own field layout, plus a few
              changes made &ldquo;in Zoho&rdquo; since the last export. Pointing Neura1 at a real Zoho MCP server is a setting
              (<code className="font-mono text-[11.5px]">NEURA1_ERP_MCP_URL</code>), not new code.
            </p>
          )}
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {(c?.source.reads ?? []).map((r) => (
              <div key={r} className="flex items-center gap-2 text-[13px]"><CheckCircle2 size={14} className="text-success" /> {r}</div>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            <button disabled={!canSync || !!busy} onClick={async () => setProbe(await go("probe", "/api/connect/zoho/test"))}
                    className={`${btn} border border-line bg-elev hover:border-line2`}>
              {busy === "probe" ? <Loader2 size={14} className="animate-spin" /> : <Plug size={14} />} Test connection
            </button>
            <button disabled={!canSync || !!busy} onClick={() => sync(true)} className={`${btn} border border-line bg-elev hover:border-line2`}>
              {busy === "preview" ? <Loader2 size={14} className="animate-spin" /> : <GitCompareArrows size={14} />} Preview changes
            </button>
            <button disabled={!canSync || !!busy} onClick={() => sync(false)} className={`${btn} bg-accent text-accent-ink hover:bg-accent-hover`}>
              {busy === "sync" ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Sync now
            </button>
          </div>
          {!canSync && c && <p className="mt-2 text-[12px] text-faint"><Lock size={11} className="mr-1 inline" />The directors and leadership can test and run a sync.</p>}
          {(busy === "preview" || busy === "sync") && <p className="mt-2 text-[12px] text-muted">Reading Zoho over MCP: items, purchase orders, goods received, projects and tasks…</p>}

          <AnimatePresence>
            {probe && (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-4 rounded-xl border border-line p-3 text-[12.5px]">
                {probe.ok ? <>
                  <div className="flex items-center gap-2 font-medium text-success"><CheckCircle2 size={14} /> Connected. The server offers {probe.tools?.length} tools:</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">{probe.tools?.map((t) => <span key={t.name} title={t.description} className="rounded-full border border-line px-2 py-0.5 font-mono text-[11px] text-muted">{t.name}</span>)}</div>
                </> : <div className="flex items-center gap-2 text-danger"><XCircle size={14} /> {probe.error}</div>}
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {preview && (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-4 rounded-xl border border-line">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2 text-[12.5px]">
                  <span className="font-medium">{preview.dry_run ? "Preview: nothing written yet" : preview.ok ? (preview.message ?? "Synced") : "Not synced"}</span>
                  {preview.read && <span className="text-faint">Read {Object.entries(preview.read).filter(([, n]) => n).map(([k, n]) => `${n} ${READ_LABEL[k] ?? k}`).join(" · ")}</span>}
                </div>
                {preview.error && <div className="px-3 py-2 text-[12.5px] text-danger">{preview.error}</div>}
                {preview.changes && preview.changes.length === 0 && <div className="px-3 py-3 text-[13px] text-muted">{preview.message}</div>}
                <ul className="divide-y divide-line">
                  {preview.changes?.map((ch, n) => (
                    <motion.li key={ch.kind + ch.id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: n * 0.04 }}
                               className="flex items-start gap-3 px-3 py-2.5 text-[12.5px]">
                      <span className="w-[68px] shrink-0"><Pill tone={ch.change === "new" ? "success" : "accent"}>{ch.change === "new" ? "New" : "Changed"}</Pill></span>
                      <div className="min-w-0 flex-1">
                        <div><span className="text-muted">{KIND_LABEL[ch.kind] ?? ch.kind}</span> <span className="font-mono text-[12px]">{ch.id}</span></div>
                        {Object.entries(ch.fields).map(([f, [a, b]]) => (
                          <div key={f} className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12px]">
                            <span className="text-faint">{f.replace("_", " ")}</span>
                            <span className="rounded bg-danger/10 px-1 text-danger line-through decoration-danger/50">{a || "empty"}</span>
                            <ArrowRight size={11} className="text-faint" />
                            <span className="rounded bg-success/12 px-1 text-success">{b || "empty"}</span>
                          </div>
                        ))}
                        {ch.change === "new" && <div className="mt-0.5 text-[12px] text-muted">{ch.summary.replace(/^New [^:]+: ?/, "")}</div>}
                      </div>
                    </motion.li>
                  ))}
                </ul>
                {!!preview.warnings?.length && <div className="border-t border-line px-3 py-2 text-[12px] text-warn">{preview.warnings.join(" · ")}</div>}
              </motion.div>
            )}
          </AnimatePresence>

          <div className="mt-5">
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-faint">Sync history</div>
            {c && c.runs.length === 0 && <p className="text-[12.5px] text-muted">No syncs yet.</p>}
            <ul className="space-y-1.5">
              {c?.runs.map((r) => (
                <li key={r.id} className="flex items-center gap-2 text-[12.5px]">
                  <CheckCircle2 size={13} className="text-success" />
                  <span className="num">{when(r.at)}</span>
                  <span className="text-muted">· {r.changes} change{r.changes === 1 ? "" : "s"}{r.by ? ` · by ${r.by}` : ""}</span>
                  <span className="ml-auto font-mono text-[11px] text-faint">{r.id}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Agents */}
        <section className="card flex flex-col p-5">
          <header className="flex flex-wrap items-start gap-3">
            <span className="rounded-xl bg-violet/12 p-2.5 text-violet"><Bot size={18} /></span>
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-semibold tracking-tight">OpenAI Dots and other agents</div>
              <div className="mt-0.5 text-[12.5px] text-muted">Remote MCP · {agents?.mcp.transport ?? "Streamable HTTP"} · read-only</div>
            </div>
            {agents && (agents.mcp.enabled ? <Pill tone="success" dot>On</Pill> : <Pill dot>Off</Pill>)}
          </header>
          <p className="mt-3 text-[13px] text-muted">
            Dots are OpenAI&apos;s always-on agents: they keep working on a goal and talk to the team in Slack and Teams. They reach
            outside tools through plugins built on MCP. Neura1 offers itself as one, so a Dot can watch the plan
            (&ldquo;tell #ops every morning what slipped and why&rdquo;) and answer from the company graph instead of guessing.
          </p>

          <div className="mt-4 rounded-xl border border-line bg-elev p-3">
            <div className="text-[11px] font-medium uppercase tracking-wider text-faint">Endpoint</div>
            <div className="mt-1 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate font-mono text-[12.5px]">&lt;your Neura1 address&gt;{agents?.mcp.path ?? "/api/agent/mcp"}</code>
              <button aria-label="Copy path" onClick={() => navigator.clipboard?.writeText(agents?.mcp.path ?? "/api/agent/mcp").then(() => toast.success("Copied"), () => {})}
                      className="rounded-lg p-1.5 text-muted hover:bg-panel hover:text-ink"><Copy size={13} /></button>
            </div>
            <div className="mt-1.5 text-[12px] text-muted">Token in an <code className="font-mono">Authorization: Bearer</code> header, or as a path segment for clients that only take a URL.</div>
          </div>

          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-[13px]">
            <div className="flex items-center gap-2 whitespace-nowrap"><ShieldCheck size={14} className="text-accent" /> Reads as <b className="font-medium">{agents?.mcp.read_as ?? "…"}</b></div>
            <div className="flex items-center gap-2">{agents?.mcp.sees_money ? <Eye size={14} className="text-warn" /> : <EyeOff size={14} className="text-success" />} Amounts {agents?.mcp.sees_money ? "visible" : "hidden"}</div>
            <div className="flex items-center gap-2">{agents?.mcp.sees_leave ? <Eye size={14} className="text-warn" /> : <EyeOff size={14} className="text-success" />} Leave {agents?.mcp.sees_leave ? "visible" : "hidden"}</div>
          </div>

          <div className="mt-4">
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-faint">{agents?.mcp.tools.length ?? 0} tools offered</div>
            <div className="flex flex-wrap gap-1.5">{agents?.mcp.tools.map((t) => <span key={t.name} title={t.description} className="rounded-full border border-line px-2 py-0.5 font-mono text-[11px] text-muted">{t.name}</span>)}</div>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            <button disabled={!canSync || !!busy || !agents?.mcp.enabled} onClick={async () => setAgentTest(await go("agent", "/api/agents/test"))}
                    className={`${btn} border border-line bg-elev hover:border-line2`}>
              {busy === "agent" ? <Loader2 size={14} className="animate-spin" /> : <PlugZap size={14} />} Test as an agent
            </button>
            <button disabled={!canSync || !!busy} onClick={async () => setAlert(await go("alert", "/api/agents/alert"))}
                    className={`${btn} border border-line bg-elev hover:border-line2`}>
              {busy === "alert" ? <Loader2 size={14} className="animate-spin" /> : <MessageSquare size={14} />} Send a plan check to Slack/Teams
            </button>
          </div>
          {agents && !agents.mcp.enabled && (
            <p className="mt-2 text-[12px] text-faint">Off. Set <code className="font-mono">NEURA1_AGENT_MCP_TOKEN</code> to turn it on. Turning it on sends answers to the agent&apos;s provider; leave it off to keep everything on premises.</p>
          )}

          <AnimatePresence>
            {agentTest && (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-4 rounded-xl border border-line p-3 text-[12.5px]">
                {agentTest.ok ? <>
                  <div className="flex items-center gap-2 font-medium text-success"><CheckCircle2 size={14} /> An MCP client connected over HTTP and called timeline_deviations.</div>
                  <div className="mt-1 text-muted">It read as {agentTest.sample?.read_as}: {agentTest.sample?.summary.late} items late, {agentTest.sample?.summary.projects_late} project past target.</div>
                </> : <div className="flex items-center gap-2 text-danger"><XCircle size={14} /> {agentTest.error}</div>}
              </motion.div>
            )}
            {alert && (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-4 rounded-xl border border-line text-[12.5px]">
                <div className="flex items-center gap-2 border-b border-line px-3 py-2 font-medium">
                  {alert.sent ? <><CheckCircle2 size={14} className="text-success" /> Posted to the channel</> : <><Sparkles size={14} className="text-accent" /> The message ({alert.reason ?? "not sent"})</>}
                </div>
                <pre className="whitespace-pre-wrap px-3 py-2 font-sans text-[12.5px] text-muted">{alert.text}</pre>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="mt-5 border-t border-line pt-4 text-[12.5px] text-muted">
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-faint">Set up a Dot</div>
            <ol className="list-decimal space-y-1 pl-5">
              <li>Set <code className="font-mono">NEURA1_AGENT_MCP_TOKEN</code> (and, if the Dot may see more, <code className="font-mono">NEURA1_AGENT_VIEWER</code>).</li>
              <li>Add Neura1 to ChatGPT as a plugin using the endpoint above.</li>
              <li>Give a Dot a standing goal, for example: &ldquo;Each morning, call timeline_deviations and post anything new that slipped, with the reason, in #ops.&rdquo;</li>
            </ol>
            <p className="mt-2 text-faint">Built on the open MCP standard Dots plugins use, and tested here with an MCP client over HTTP. It has not been tried with a live Dot, which needs a paid OpenAI plan.</p>
          </div>
        </section>
      </div>
    </div>
  );
}

/** How Neura1 sits between the systems a company already has and the agents it works with. */
function Flow() {
  const nodes = [
    { x: 90, title: "Zoho Inventory", sub: "items · POs · receipts" },
    { x: 90, title: "Zoho Projects", sub: "projects · tasks · dates", y: 1 },
    { x: 400, title: "Neura1 Connect", sub: "map · diff · validate · load", hub: true },
    { x: 690, title: "Company graph", sub: "FalkorDB", hub: true },
    { x: 990, title: "Dots · ChatGPT · Claude", sub: "remote MCP, read-only" },
    { x: 990, title: "Slack · Teams", sub: "plan checks", y: 1 },
  ];
  const Y = [44, 120];
  const mid = 82;
  const edges = [
    `M 180 ${Y[0]} C 260 ${Y[0]}, 260 ${mid}, 320 ${mid}`, `M 180 ${Y[1]} C 260 ${Y[1]}, 260 ${mid}, 320 ${mid}`,
    `M 480 ${mid} L 610 ${mid}`,
    `M 770 ${mid} C 840 ${mid}, 840 ${Y[0]}, 900 ${Y[0]}`, `M 770 ${mid} C 840 ${mid}, 840 ${Y[1]}, 900 ${Y[1]}`,
  ];
  return (
    <div data-tour="connect" className="card overflow-x-auto p-4" data-lenis-prevent>
      <svg viewBox="0 0 1080 164" className="h-auto w-full min-w-[760px]" role="img"
           aria-label="Zoho Inventory and Zoho Projects flow over MCP into Neura1 Connect, then the company graph, which agents and channels read">
        {edges.map((d, i) => (
          <g key={d}>
            <path d={d} fill="none" stroke="var(--line2)" strokeWidth={1.5} />
            <path d={d} fill="none" stroke={i < 3 ? "var(--accent)" : "var(--violet)"} strokeWidth={1.6} className="ripple-flow" />
          </g>
        ))}
        <text x={250} y={mid - 10} textAnchor="middle" fontSize={10.5} fill="var(--faint)" fontFamily="var(--font-geist-mono)">MCP</text>
        <text x={840} y={mid - 10} textAnchor="middle" fontSize={10.5} fill="var(--faint)" fontFamily="var(--font-geist-mono)">MCP · webhooks</text>
        {nodes.map((n, i) => {
          const y = n.hub ? mid : Y[n.y ?? 0];
          const w = n.hub ? 160 : 180;
          return (
            <motion.g key={n.title} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.08, duration: 0.5 }}>
              <rect x={n.x - w / 2} y={y - 24} width={w} height={48} rx={14} fill="var(--panel)"
                    stroke={n.hub ? "var(--accent)" : "var(--line2)"} strokeOpacity={n.hub ? 0.6 : 1} />
              <text x={n.x} y={y - 3} textAnchor="middle" fontSize={13} fontWeight={600} fill="var(--ink)">{n.title}</text>
              <text x={n.x} y={y + 13} textAnchor="middle" fontSize={10.5} fill="var(--muted)">{n.sub}</text>
            </motion.g>
          );
        })}
      </svg>
    </div>
  );
}
