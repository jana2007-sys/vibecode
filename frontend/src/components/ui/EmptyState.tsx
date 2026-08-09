/** Graceful empty / error state panel. */

import { type ReactNode } from "react";
import { AlertCircleIcon, InboxIcon } from "./Icons";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: "inbox" | "alert";
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  title,
  description,
  icon = "inbox",
  action,
  className,
}: EmptyStateProps) {
  const Icon = icon === "alert" ? AlertCircleIcon : InboxIcon;

  return (
    <div
      className={`flex flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-teal-400/30 bg-white/50 px-6 py-14 text-center dark:border-teal-400/25 dark:bg-[#0B2538]/40 ${className ?? ""}`}
    >
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-teal-400/30 bg-gradient-to-br from-teal-500/10 to-cyan-500/10 text-teal-600 shadow-[0_0_30px_-10px_rgba(20,184,166,0.35)] dark:text-teal-200 dark:shadow-[0_0_30px_-10px_rgba(20,184,166,0.4)]">
        <Icon className="h-7 w-7" />
      </div>
      <div className="space-y-1.5">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-white">{title}</h3>
        {description ? (
          <p className="mx-auto max-w-md text-sm leading-relaxed text-slate-500 dark:text-slate-400">
            {description}
          </p>
        ) : null}
      </div>
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  );
}
