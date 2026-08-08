/** Shared page footer. */

export function Footer() {
  return (
    <footer className="border-t border-white/5 bg-ink-950/40">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-center justify-between gap-2 px-4 py-6 text-sm text-slate-500 sm:flex-row sm:px-6 lg:px-8">
        <p>InterVue AI — Your AI-powered technical interview coach.</p>
        <p className="text-xs text-slate-600">
          Curriculum-grounded · Context-aware · Gemini-powered
        </p>
      </div>
    </footer>
  );
}
