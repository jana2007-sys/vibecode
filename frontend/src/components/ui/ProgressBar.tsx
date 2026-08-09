/** Animated progress bar. */

interface ProgressBarProps {
  /** Current value (0..max). */
  value: number;
  max: number;
  className?: string;
  ariaLabel?: string;
}

export function ProgressBar({
  value,
  max,
  className,
  ariaLabel = "Interview progress",
}: ProgressBarProps) {
  const safeMax = max > 0 ? max : 1;
  const fraction = Math.max(0, Math.min(1, value / safeMax));
  const percent = Math.round(fraction * 100);

  return (
    <div
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={ariaLabel}
      className={`h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-white/10 ${className ?? ""}`}
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-teal-400 via-cyan-500 to-sky-400 shadow-[0_0_12px_rgba(6,182,212,0.55)] transition-all duration-700 ease-out"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
