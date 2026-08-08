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
      className={`flex flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-white/15 bg-white/[0.03] px-6 py-14 text-center ${className ?? ""}`}
    >
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-slate-400">
        <Icon className="h-7 w-7" />
      </div>
      <div className="space-y-1.5">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        {description ? (
          <p className="mx-auto max-w-md text-sm leading-relaxed text-slate-400">
            {description}
          </p>
        ) : null}
      </div>
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  );
}
