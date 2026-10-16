"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { setChoice, useThemeChoice, type ThemeChoice } from "@/lib/theme";

const OPTIONS: [ThemeChoice, typeof Sun, string][] = [["system", Monitor, "Match system"], ["light", Sun, "Light"], ["dark", Moon, "Dark"]];

export default function ThemeSwitch() {
  const choice = useThemeChoice();
  return (
    <div role="radiogroup" aria-label="Theme" className="flex rounded-lg border border-line bg-elev p-0.5">
      {OPTIONS.map(([value, Icon, label]) => (
        <button key={value} role="radio" aria-checked={choice === value} title={label} onClick={() => setChoice(value)}
                className={`rounded-md p-1 transition ${choice === value ? "bg-panel text-ink shadow-[var(--shadow)]" : "text-faint hover:text-ink"}`}>
          <Icon size={13} />
        </button>
      ))}
    </div>
  );
}
