"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ViewTransition, useEffect, useState } from "react";
import Lenis from "lenis";
import { motion } from "motion/react";
import { Toaster } from "sonner";
import {
  Bell, Brain, Building2, ChevronRight, FileText, FolderKanban, History, Inbox, KanbanSquare, LayoutDashboard, Menu, MessageCircle,
  Compass, Network, Radar, Search, Sparkles, Sun, Target, Upload, Users, Waypoints,
} from "lucide-react";
import CommandPalette from "@/components/CommandPalette";
import ThemeSwitch from "@/components/ThemeSwitch";
import Tour, { startTour } from "@/components/Tour";
import ViewerSwitch from "@/components/ViewerSwitch";
import { api } from "@/lib/api";
import { useResolvedTheme } from "@/lib/theme";

type Item = { href: string; label: string; icon: typeof Sun; badge?: "signals" };
const NAV: { section: string; items: Item[]; collapsible?: boolean }[] = [
  { section: "Today", items: [
    { href: "/", label: "Overview", icon: LayoutDashboard },
    { href: "/me", label: "My day", icon: Sun },
    { href: "/signals", label: "Signals", icon: Inbox, badge: "signals" },
    { href: "/board", label: "Workboard", icon: KanbanSquare },
    { href: "/chat", label: "Chat", icon: MessageCircle },
  ]},
  { section: "Company brain", items: [
    { href: "/brain", label: "Ask & search", icon: Brain },
    { href: "/docs", label: "Documents", icon: FileText },
    { href: "/explore", label: "Graph explorer", icon: Waypoints },
    { href: "/capabilities", label: "Capability map", icon: Target },
    { href: "/risk", label: "Risk radar", icon: Radar },
  ]},
  { section: "Company", items: [
    { href: "/people", label: "People", icon: Users },
    { href: "/org", label: "Organisation", icon: Network },
    { href: "/projects", label: "Projects", icon: FolderKanban },
    { href: "/customers", label: "Customers", icon: Building2 },
  ]},
  { section: "More", collapsible: true, items: [
    { href: "/history", label: "Plans", icon: History },
    { href: "/changes", label: "What's new", icon: Bell },
    { href: "/import", label: "Import", icon: Upload },
  ]},
];

const openPalette = () => window.dispatchEvent(new Event("neura1:palette"));

export default function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const theme = useResolvedTheme();
  const [mobile, setMobile] = useState(false);
  const [openSignals, setOpenSignals] = useState(0);
  const [moreOpen, setMoreOpen] = useState(false);

  // Momentum scrolling for the page. Anything that scrolls on its own (lists, chat, the editor, graphs) keeps native scroll.
  useEffect(() => {
    // Reduced-motion users and automated browsers (screen readers' test rigs, Playwright) keep native scrolling.
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || navigator.webdriver) return;
    const lenis = new Lenis({
      autoRaf: true, lerp: 0.11, wheelMultiplier: 1,
      prevent: (node) => {
        if (node.closest?.(".react-flow, .superdoc, [data-lenis-prevent]")) return true;
        const st = getComputedStyle(node);
        return /(auto|scroll)/.test(st.overflowY) && node.scrollHeight > node.clientHeight + 1;
      },
    });
    (window as unknown as { lenis?: Lenis }).lenis = lenis;
    return () => lenis.destroy();
  }, []);
  useEffect(() => {
    (window as unknown as { lenis?: Lenis }).lenis?.scrollTo(0, { immediate: true });
  }, [path]);

  // A soft light follows the cursor across whichever card it is over.
  useEffect(() => {
    let frame = 0;
    const move = (e: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const card = (e.target as Element | null)?.closest?.(".card") as HTMLElement | null;
        if (!card) return;
        const r = card.getBoundingClientRect();
        card.style.setProperty("--mx", `${e.clientX - r.left}px`);
        card.style.setProperty("--my", `${e.clientY - r.top}px`);
      });
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => { window.removeEventListener("pointermove", move); cancelAnimationFrame(frame); };
  }, []);

  useEffect(() => {
    api<{ investigation: unknown }[]>("/api/signals").then((s) => setOpenSignals(s.filter((x) => !x.investigation).length)).catch(() => {});
  }, [path]);

  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href)) ||
    (href === "/signals" && path.startsWith("/impact"));
  const here = NAV.flatMap((g) => g.items.map((i) => ({ ...i, section: g.section }))).find((i) => active(i.href));

  const sidebar = (
    <div className="flex h-full flex-col">
      <Link href="/" onClick={() => setMobile(false)} className="mx-3 mt-3 flex items-center gap-2.5 rounded-xl px-2 py-2 hover:bg-elev">
        <Image src="/mark.png" alt="" width={256} height={207} loading="eager" style={{ width: 28, height: "auto" }} />
        <span className="min-w-0 leading-tight">
          <span className="block truncate text-[13.5px] font-semibold tracking-tight">Flyvi Technologies</span>
          <span className="block text-[11.5px] text-muted">Neura1 · company brain</span>
        </span>
      </Link>
      <button onClick={openPalette}
              className="mx-3 mt-2 flex items-center gap-2 rounded-lg border border-line bg-elev px-2.5 py-1.5 text-[13px] text-muted transition hover:border-line2 hover:text-ink">
        <Search size={14} /> <span className="flex-1 text-left">Search or ask</span> <span className="kbd">⌘K</span>
      </button>
      <nav className="isolate mt-3 flex-1 space-y-4 overflow-y-auto px-3 pb-3">
        {NAV.map((g) => {
          const shut = g.collapsible && !moreOpen && !g.items.some((i) => active(i.href));
          return (
          <div key={g.section}>
            {g.collapsible ? (
              <button onClick={() => setMoreOpen(!moreOpen)} aria-expanded={!shut}
                      className="flex w-full items-center gap-1 px-2 pb-1 text-[11px] font-medium text-faint hover:text-ink-soft">
                {g.section} <ChevronRight size={11} className={`transition-transform ${shut ? "" : "rotate-90"}`} />
              </button>
            ) : <div className="px-2 pb-1 text-[11px] font-medium text-faint">{g.section}</div>}
            {!shut && <ul className="space-y-px">
              {g.items.map(({ href, label, icon: Icon, badge }) => {
                const on = active(href);
                return (
                  <li key={href}>
                    <Link href={href} onClick={() => setMobile(false)}
                          className={`group relative flex h-8 items-center gap-2.5 rounded-lg px-2 text-[13.5px] transition-colors ${on
                            ? "font-medium text-ink"
                            : "text-ink-soft hover:bg-elev hover:text-ink"}`}>
                      {on && (
                        <motion.span layoutId="nav-active" className="absolute inset-0 -z-10 rounded-lg bg-elev-strong shadow-[0_1px_0_0_var(--edge)_inset]"
                                     transition={{ type: "spring", stiffness: 520, damping: 42, mass: 0.8 }}>
                          <span className="absolute -left-3 top-1.5 h-5 w-[3px] rounded-r-full bg-accent" />
                        </motion.span>
                      )}
                      <Icon size={15} strokeWidth={on ? 2.1 : 1.8} className={on ? "text-accent" : "text-muted group-hover:text-ink-soft"} />
                      <span className="flex-1 truncate">{label}</span>
                      {badge === "signals" && openSignals > 0 && (
                        <span className="num min-w-[18px] rounded-full bg-accent/15 px-1.5 text-center text-[11px] font-medium text-accent">{openSignals}</span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>}
          </div>
          );
        })}
      </nav>
      <div className="space-y-2 border-t border-line p-3">
        <ViewerSwitch />
        <div className="flex items-center justify-between px-1">
          <span className="flex items-center gap-1.5 text-[11px] text-faint"><span className="h-1.5 w-1.5 rounded-full bg-warn" /> Synthetic data</span>
          <ThemeSwitch />
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen">
      <div aria-hidden className="aurora"><span /><span /><span /></div>
      <aside className="glass-bar sticky top-0 z-20 hidden h-screen w-[248px] shrink-0 border-r border-line lg:block">
        {sidebar}
      </aside>

      {mobile && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button aria-label="Close menu" className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setMobile(false)} />
          <aside className="surface-pop absolute inset-y-2 left-2 w-[264px] overflow-hidden">{sidebar}</aside>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <header className="glass-bar sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-line px-4 lg:px-8">
          <button aria-label="Menu" onClick={() => setMobile(true)} className="-ml-1 rounded-lg p-1.5 text-muted hover:bg-elev hover:text-ink lg:hidden"><Menu size={17} /></button>
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-[13px]">
            <span className="hidden text-muted sm:inline">Flyvi</span>
            <span className="hidden text-faint sm:inline">/</span>
            <span className="hidden text-muted sm:inline">{here?.section ?? "Neura1"}</span>
            <span className="hidden text-faint sm:inline">/</span>
            <span className="truncate font-medium">{here?.label ?? "Neura1"}</span>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button onClick={startTour} className="hidden items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] text-muted transition hover:bg-elev hover:text-ink sm:flex">
              <Compass size={14} /> Take the tour
            </button>
            <button onClick={openPalette}
                    className="ai-ring flex items-center gap-1.5 rounded-full bg-panel px-3 py-1.5 text-[13px] font-medium shadow-[var(--shadow)] transition hover:bg-elev">
              <Sparkles size={14} className="text-accent" /> Ask Neura1
              <span className="kbd ml-1 hidden sm:inline">⌘K</span>
            </button>
          </div>
        </header>
        <main className="mx-auto max-w-[1360px] px-4 pb-16 pt-6 lg:px-8 lg:pt-8">
          <ViewTransition name="page">
            <div key={path} className="rise">{children}</div>
          </ViewTransition>
        </main>
      </div>
      <CommandPalette />
      <Tour />
      <Toaster theme={theme} position="bottom-right" toastOptions={{ className: "!rounded-xl !border-line !bg-panel !text-ink !shadow-[var(--shadow-pop)]" }} />
    </div>
  );
}
