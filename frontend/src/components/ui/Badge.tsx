/** Reusable pill badge with tone variants. */

import { type ReactNode } from "react";

type Tone = "teal" | "cyan" | "sky" | "emerald" | "amber" | "rose" | "slate";

export interface BadgeProps {
  tone?: Tone;
  className?: string;
  children: ReactNode;
}

const toneClasses: Record<Tone, string> = {
  teal:
    "border-teal-400/40 bg-teal-50 text-teal-700 dark:border-teal-400/30 dark:bg-teal-500/15 dark:text-teal-200",
  cyan:
    "border-cyan-400/40 bg-cyan-50 text-cyan-700 dark:border-cyan-400/30 dark:bg-cyan-500/15 dark:text-cyan-200",
  sky:
    "border-sky-400/40 bg-sky-50 text-sky-700 dark:border-sky-400/30 dark:bg-sky-500/15 dark:text-sky-200",
  emerald:
    "border-emerald-400/40 bg-emerald-50 text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-500/15 dark:text-emerald-200",
  amber:
    "border-amber-400/40 bg-amber-50 text-amber-700 dark:border-amber-400/30 dark:bg-amber-500/15 dark:text-amber-200",
  rose: "border-rose-400/40 bg-rose-50 text-rose-700 dark:border-rose-400/30 dark:bg-rose-500/15 dark:text-rose-200",
  slate:
    "border-slate-300 bg-slate-100 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300",
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
