"use client";

import Link from "next/link";
import { animate, motion, useInView, useMotionValue, useTransform } from "motion/react";
import { ArrowUpRight } from "lucide-react";
import React, { useEffect, useRef } from "react";

/** A number that counts up once when it first comes into view. */
export function Ticker({ value, className = "", format = (n: number) => Math.round(n).toLocaleString("en-IN") }:
  { value: number; className?: string; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => format(v));
  useEffect(() => {
    if (!inView) return;
    const c = animate(mv, value, { duration: 0.9, ease: [0.16, 1, 0.3, 1] });
    return () => c.stop();
  }, [inView, mv, value]);
  return <motion.span ref={ref} className={`num ${className}`}>{text}</motion.span>;
}

/** A titled surface. Hierarchy comes from the header row, not from extra borders inside. */
export function Section({ title, icon: Icon, action, href, children, className = "", bodyClass = "p-5 pt-3" }: {
  title: React.ReactNode; icon?: React.ComponentType<{ size?: number; className?: string }>; action?: string; href?: string;
  children: React.ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={`card flex min-w-0 flex-col ${className}`}>
      <header className="flex items-center justify-between gap-3 px-5 pt-4">
        <h2 className="flex items-center gap-2 text-[14px] font-semibold tracking-tight">
          {Icon && <Icon size={15} className="text-muted" />} {title}
        </h2>
        {href && action && (
          <Link href={href} className="group flex items-center gap-0.5 text-[12.5px] text-muted transition hover:text-ink">
            {action} <ArrowUpRight size={13} className="transition group-hover:-translate-y-px group-hover:translate-x-px" />
          </Link>
        )}
      </header>
      <div className={`flex-1 ${bodyClass}`}>{children}</div>
    </section>
  );
}

const TONES = {
  neutral: "bg-elev text-ink-soft",
  accent: "bg-accent/12 text-accent",
  success: "bg-success/12 text-success",
  warn: "bg-warn/14 text-warn",
  danger: "bg-danger/12 text-danger",
  violet: "bg-violet/12 text-violet",
} as const;
export type Tone = keyof typeof TONES;

export function Pill({ tone = "neutral", children, dot = false }: { tone?: Tone; children: React.ReactNode; dot?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11.5px] font-medium ${TONES[tone]}`}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}{children}
    </span>
  );
}

/** Children rise in one after another. */
export function Stagger({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <motion.div className={className} initial="hidden" animate="show"
                variants={{ hidden: {}, show: { transition: { staggerChildren: 0.05 } } }}>
      {children}
    </motion.div>
  );
}
export const riseItem = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.42, ease: [0.16, 1, 0.3, 1] as const } },
};

const wordVariant = {
  hidden: { opacity: 0, y: "0.4em", filter: "blur(10px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.75, ease: [0.16, 1, 0.3, 1] as const } },
};

/** A page headline whose words rise out of a blur, one after another. Strings are split into words; elements
 *  (such as an <em> accent) move as one word. Done in React, so re-renders stay safe. */
export function PageTitle({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  let k = 0;
  const parts: React.ReactNode[] = [];
  for (const child of React.Children.toArray(children)) {
    if (typeof child === "string" || typeof child === "number") {
      for (const w of String(child).split(/(\s+)/)) {
        if (!w) continue;
        parts.push(/^\s+$/.test(w) ? " " : <motion.span key={k++} className="split-word" variants={wordVariant}>{w}</motion.span>);
      }
    } else {
      parts.push(<motion.span key={k++} className="split-word" variants={wordVariant}>{child}</motion.span>);
    }
  }
  return (
    <motion.h1 className={`page-title ${className}`} initial="hidden" animate="show"
               variants={{ hidden: {}, show: { transition: { staggerChildren: 0.05 } } }}>
      {parts}
    </motion.h1>
  );
}
