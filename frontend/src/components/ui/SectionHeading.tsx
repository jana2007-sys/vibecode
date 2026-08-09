/** Section heading with optional eyebrow and subtitle. */

import { type ReactNode } from "react";

interface SectionHeadingProps {
  eyebrow?: string;
  title: ReactNode;
  subtitle?: ReactNode;
  align?: "center" | "left";
  className?: string;
}

export function SectionHeading({
  eyebrow,
  title,
  subtitle,
  align = "center",
  className,
}: SectionHeadingProps) {
  const alignClasses =
    align === "center" ? "text-center items-center" : "text-left items-start";

  return (
    <div className={`flex flex-col gap-3 ${alignClasses} ${className ?? ""}`}>
      {eyebrow ? (
        <span className="inline-flex items-center gap-2 rounded-full border border-teal-400/40 bg-teal-50 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-teal-700 shadow-[0_0_20px_-6px_rgba(20,184,166,0.35)] dark:border-teal-400/30 dark:bg-teal-500/10 dark:text-teal-200">
          <span className="h-1.5 w-1.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-500 dark:from-teal-400 dark:to-cyan-400" />
          {eyebrow}
        </span>
      ) : null}
      <h2 className="text-balance text-3xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-4xl">
        {title}
      </h2>
      {subtitle ? (
        <p className="max-w-2xl text-pretty text-base leading-relaxed text-slate-500 dark:text-slate-400">
          {subtitle}
        </p>
      ) : null}
    </div>
  );
}
