/** Reusable loading indicator. */

interface LoadingProps {
  label?: string;
}

export function Loading({ label = "Loading..." }: LoadingProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-3 py-16 text-slate-500"
    >
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-brand border-t-transparent" />
      <span>{label}</span>
    </div>
  );
}
