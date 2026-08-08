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
      className={`h-1.5 w-full overflow-hidden rounded-full bg-white/10 ${className ?? ""}`}
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 shadow-[0_0_12px_rgba(139,92,246,0.6)] transition-all duration-700 ease-out"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
