"use client";

import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, ArrowRight, Compass, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const NOTICE = "/impact?source=inbox%2Fnotice_NB54360_2026-10-14.md";

type Step = { path: string; target?: string; title: string; body: string };

/** The 3-minute story, for a first visit or a judge: one supplier notice, followed through the whole company. */
const STEPS: Step[] = [
  { path: "/", target: "ripple", title: "A supplier notice arrives",
    body: "Deccan Components raises the price of the NB54360 regulator and stretches its lead time to 22 weeks. Watch one FalkorDB traversal carry it through Flyvi: product revisions, builds, customer orders, customers and the people who own them." },
  { path: NOTICE, target: "headline", title: "What it means, in one view",
    body: "3 of 3 builds at risk, 3 customer orders exposed, one with a penalty clause, and a cost increase of ₹37,400 computed by code from the bill of materials, stock and quotes." },
  { path: NOTICE, target: "rejected", title: "The company remembers",
    body: "The cheaper pin-compatible part was already rejected in March 2025 (DEC-117) after it shut down at 68 °C. The model found that decision in Slack and Jira; code checked every quote word for word." },
  { path: NOTICE, target: "actions", title: "Every team gets its task",
    body: "Tasks come from Flyvi's own change policy (HB-ENG-04): engineering reviews, the firmware owner, requalification, procurement, production and sales. Approve once and they land on the Workboard." },
  { path: "/chat", target: "chat", title: "The team works inside the brain",
    body: "Type \u201cCan we go for NB54361-L to save cost?\u201d: before you send, Neura1 remembers that the company rejected it in 2025, and shows the Slack messages that prove it. Messages become linked knowledge, /impact and /who answer from the graph, and replies only include what every reader may see." },
  { path: "/docs", target: "templates", title: "Documents written with the brain",
    body: "A change notice, customer response or handover note is written from the graph into a real Word document. Check facts catches rejected parts, expired quotes and obsolete revisions; Edit with AI suggests tracked changes." },
  { path: "/capabilities", target: "thin", title: "What Flyvi is good at, and where it is thin",
    body: "Built from recorded work, with no scores or rankings. Power sequencing is held by one person, and the NB54360 firmware review depends on it. Names are visible only to people allowed to see them." },
  { path: "/sandbox", target: "sandbox", title: "Try it on a copy of Flyvi first",
    body: "Pick \u201cThe perfect storm\u201d. FalkorDB copies the whole company graph in about a tenth of a second; the change runs on the copy, each part alone and then together, and the copy is thrown away. What only goes wrong in combination is called out: here, the firmware review lands on Sai in the weeks Sai is away." },
  { path: "/brain", target: "ask", title: "Ask anything",
    body: "The agent plans its own graph queries, shows each step and cites its sources. On 18 blind questions it answered 15 (search alone: 10); every result and failure, including where a plain prompt did better, is published in docs/EVAL.md." },
  { path: "/", title: "That is Neura1",
    body: "One graph of Flyvi's people, products, customers, documents and decisions, kept current, permission-aware and verifiable. Explore freely: ⌘K searches or asks anything." },
];

const KEY = "neura1-tour";

export function startTour() {
  window.dispatchEvent(new Event("neura1:tour"));
}

export default function Tour() {
  const router = useRouter();
  const path = usePathname();
  const [step, setStep] = useState<number | null>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);

  const go = useCallback((i: number | null) => {
    setStep(i);
    try { if (i === null) sessionStorage.removeItem(KEY); else sessionStorage.setItem(KEY, String(i)); } catch {}
    if (i !== null && STEPS[i].path.split("?")[0] !== location.pathname) router.push(STEPS[i].path);
  }, [router]);

  useEffect(() => {
    const start = () => go(0);
    window.addEventListener("neura1:tour", start);
    try { const s = sessionStorage.getItem(KEY); if (s !== null) setTimeout(() => setStep(Number(s)), 0); } catch {}
    return () => window.removeEventListener("neura1:tour", start);
  }, [go]);

  // Find the highlighted element on the current page (it may still be loading), and follow it while scrolling.
  useEffect(() => {
    if (step === null) return;
    const s = STEPS[step];
    let raf = 0, tries = 0, el: Element | null = null, scrolled = false;
    const track = () => {
      if (!s.target) { setRect(null); return; }
      el = el ?? document.querySelector(`[data-tour="${s.target}"]`);
      if (el) {
        if (!scrolled) { el.scrollIntoView({ behavior: "smooth", block: "center" }); scrolled = true; }
        setRect(el.getBoundingClientRect());
      } else if (tries++ > 600) { setRect(null); return; }
      raf = requestAnimationFrame(track);
    };
    setTimeout(() => { raf = requestAnimationFrame(track); }, 0);
    return () => cancelAnimationFrame(raf);
  }, [step, path]);

  useEffect(() => {
    if (step === null) return;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") go(null);
      if (e.key === "ArrowRight" && step < STEPS.length - 1) go(step + 1);
      if (e.key === "ArrowLeft" && step > 0) go(step - 1);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [step, go]);

  if (step === null) return null;
  const s = STEPS[step];
  const pad = 8;
  // Keep the card clear of what it is pointing at: if the highlight sits low on the screen, put the card on top.
  const low = rect ? rect.top + rect.height / 2 > window.innerHeight / 2 : false;
  return (
    <AnimatePresence>
      <div className="pointer-events-none fixed inset-0 z-[60]" aria-live="polite">
        {rect ? (
          <motion.div className="absolute rounded-2xl ring-2 ring-accent"
                      style={{ boxShadow: "0 0 0 9999px rgb(0 0 0 / 0.45), 0 0 40px 4px color-mix(in oklch, var(--accent) 40%, transparent)" }}
                      animate={{ left: rect.left - pad, top: rect.top - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }}
                      transition={{ type: "spring", stiffness: 260, damping: 32 }} />
        ) : <div className="absolute inset-0 bg-black/35" />}
        <motion.div key={step} role="dialog" aria-label={s.title}
                    initial={{ opacity: 0, y: 12, filter: "blur(4px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                    transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                    className={`surface-pop pointer-events-auto fixed right-5 w-[min(420px,calc(100vw-2.5rem))] p-5 ${low ? "top-16" : "bottom-5"}`}>
          <div className="flex items-center justify-between text-[12px] text-muted">
            <span className="flex items-center gap-1.5"><Compass size={13} className="text-accent" /> Tour · {step + 1} of {STEPS.length}</span>
            <button onClick={() => go(null)} aria-label="End the tour" className="rounded-md p-1 hover:bg-elev hover:text-ink"><X size={14} /></button>
          </div>
          <div className="mt-2 text-[17px] font-semibold tracking-tight">{s.title}</div>
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-soft">{s.body}</p>
          <div className="mt-4 flex items-center gap-1">
            {STEPS.map((_, i) => <span key={i} className={`h-1 flex-1 rounded-full ${i <= step ? "bg-accent" : "bg-elev-strong"}`} />)}
          </div>
          <div className="mt-4 flex items-center justify-between">
            <button disabled={step === 0} onClick={() => go(step - 1)}
                    className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[13px] text-muted hover:bg-elev hover:text-ink disabled:opacity-30"><ArrowLeft size={14} /> Back</button>
            {step < STEPS.length - 1
              ? <button onClick={() => go(step + 1)} className="flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[13px] font-medium text-accent-ink hover:bg-accent-hover">Next <ArrowRight size={14} /></button>
              : <button onClick={() => go(null)} className="rounded-lg bg-accent px-3.5 py-1.5 text-[13px] font-medium text-accent-ink hover:bg-accent-hover">Finish</button>}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
