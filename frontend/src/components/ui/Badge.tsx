/** Reusable pill badge with tone variants. */

import { type ReactNode } from "react";

type Tone = "indigo" | "violet" | "emerald" | "amber" | "rose" | "slate";

export interface BadgeProps {
  tone?: Tone;
  className?: string;
  children: ReactNode;
}

const toneClasses: Record<Tone, string> = {
  indigo:
    "border-indigo-400/30 bg-indigo-500/15 text-indigo-200",
  violet:
    "border-violet-400/30 bg-violet-500/15 text-violet-200",
  emerald:
    "border-emerald-400/30 bg-emerald-500/15 text-emerald-200",
  amber:
    "border-amber-400/30 bg-amber-500/15 text-amber-200",
  rose: "border-rose-400/30 bg-rose-500/15 text-rose-200",
  slate: "border-white/10 bg-white/5 text-slate-300",
};

export function Badge({ tone = "slate", className, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${toneClasses[tone]} ${className ?? ""}`}
    >
      {children}
    </span>
  );
}
