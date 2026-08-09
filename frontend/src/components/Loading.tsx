/** Reusable loading indicator. */

interface LoadingProps {
  label?: string;
  className?: string;
}

export function Loading({
  label = "Loading...",
  className,
}: LoadingProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-col items-center justify-center gap-4 py-16 text-slate-500 dark:text-slate-400 ${className ?? ""}`}
    >
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 animate-blink rounded-full bg-teal-400 [animation-delay:0ms]" />
        <span className="h-2 w-2 animate-blink rounded-full bg-cyan-400 [animation-delay:200ms]" />
        <span className="h-2 w-2 animate-blink rounded-full bg-sky-400 [animation-delay:400ms]" />
      </div>
      <span className="text-sm">{label}</span>
    </div>
  );
}
