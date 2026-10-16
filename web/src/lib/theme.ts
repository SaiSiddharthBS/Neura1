"use client";

import { useSyncExternalStore } from "react";

export type ThemeChoice = "system" | "light" | "dark";
const KEY = "neura1-theme";

/** Runs before first paint (inlined in <head>) so the page never flashes the wrong theme. */
export const THEME_BOOT = `try{var t=localStorage.getItem("${KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export function getChoice(): ThemeChoice {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

export function setChoice(t: ThemeChoice) {
  try { if (t === "system") localStorage.removeItem(KEY); else localStorage.setItem(KEY, t); } catch {}
  if (t === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  window.dispatchEvent(new Event("neura1:theme"));
}

function resolved(): "light" | "dark" {
  const t = document.documentElement.dataset.theme;
  if (t === "light" || t === "dark") return t;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function subscribe(cb: () => void) {
  const mq = window.matchMedia("(prefers-color-scheme: light)");
  mq.addEventListener("change", cb);
  window.addEventListener("neura1:theme", cb);
  return () => { mq.removeEventListener("change", cb); window.removeEventListener("neura1:theme", cb); };
}

/** The theme actually showing, for components that draw their own colours (graphs). */
export function useResolvedTheme(): "light" | "dark" {
  return useSyncExternalStore(subscribe, resolved, () => "dark");
}

export function useThemeChoice(): ThemeChoice {
  return useSyncExternalStore(subscribe, getChoice, () => "system");
}
