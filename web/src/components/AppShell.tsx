"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell, Brain, Building2, Command, FolderKanban, History, Inbox, KanbanSquare, LayoutDashboard, Radar, Upload, Users,
} from "lucide-react";
import CommandPalette from "@/components/CommandPalette";

const NAV = [
  { section: "Today", items: [
    { href: "/", label: "Overview", icon: LayoutDashboard },
    { href: "/signals", label: "Signals", icon: Inbox },
    { href: "/board", label: "Workboard", icon: KanbanSquare },
    { href: "/history", label: "Plans", icon: History },
  ]},
  { section: "Company brain", items: [
    { href: "/brain", label: "Ask & search", icon: Brain },
    { href: "/people", label: "People", icon: Users },
    { href: "/projects", label: "Projects", icon: FolderKanban },
    { href: "/customers", label: "Customers", icon: Building2 },
    { href: "/risk", label: "Risk radar", icon: Radar },
    { href: "/changes", label: "What's new", icon: Bell },
  ]},
  { section: "Data", items: [
    { href: "/import", label: "Import", icon: Upload },
  ]},
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href)) ||
    (href === "/signals" && path.startsWith("/impact"));

  return (
    <div className="flex min-h-screen gap-5 p-3 lg:p-5">
      <aside className="card sticky top-5 hidden h-[calc(100vh-40px)] w-60 shrink-0 flex-col lg:flex">
        <Link href="/" className="flex items-center gap-3 border-b border-line px-5 py-5">
          <Image src="/mark.png" alt="" width={40} height={32} style={{ height: "auto" }} className="drop-shadow-[0_0_12px_rgba(90,209,230,0.45)]" />
          <span>
            <span className="block text-[17px] font-semibold tracking-tight">Neura1</span>
            <span className="block text-[11px] text-muted">Company brain · Voltline</span>
          </span>
        </Link>
        <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
          {NAV.map((g) => (
            <div key={g.section}>
              <div className="px-3 pb-1.5 text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted">{g.section}</div>
              {g.items.map(({ href, label, icon: Icon }) => (
                <Link key={href} href={href}
                      className={`group flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${active(href)
                        ? "bg-accent/15 text-ink shadow-[inset_0_0_0_1px_rgba(59,130,246,0.35)]"
                        : "text-muted hover:bg-elev hover:text-ink"}`}>
                  <Icon size={16} className={active(href) ? "text-accent-hover" : ""} />
                  {label}
                </Link>
              ))}
            </div>
          ))}
        </nav>
        <div className="space-y-2 border-t border-line p-4">
          <button onClick={() => window.dispatchEvent(new Event("neura1:palette"))}
                  className="flex w-full items-center justify-between rounded-xl bg-elev px-3 py-2 text-xs text-muted hover:text-ink">
            <span className="flex items-center gap-2"><Command size={13} /> Search or ask</span>
            <kbd className="rounded border border-line px-1.5 font-mono">⌘K</kbd>
          </button>
          <div className="rounded-xl border border-warn/30 bg-warn/10 px-3 py-2 text-[11px] text-warn">Synthetic company data</div>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="card mb-4 flex items-center gap-3 px-4 py-3 lg:hidden">
          <Image src="/mark.png" alt="" width={30} height={24} style={{ height: "auto" }} />
          <span className="font-semibold">Neura1</span>
          <nav className="ml-auto flex gap-1 overflow-x-auto text-xs">
            {NAV.flatMap((g) => g.items).map((i) => (
              <Link key={i.href} href={i.href} className={`rounded-lg px-2 py-1 ${active(i.href) ? "bg-accent/20" : "text-muted"}`}>{i.label}</Link>
            ))}
          </nav>
        </header>
        <main className="rise mx-auto max-w-[1400px] pb-10">{children}</main>
      </div>
      <CommandPalette />
    </div>
  );
}
