/** Landing page shell. */

import { Link } from "react-router-dom";

export function Landing() {
  return (
    <section className="flex flex-col items-center gap-6 py-16 text-center">
      <h1 className="text-4xl font-bold tracking-tight text-slate-900">
        InterVue AI
      </h1>
      <p className="max-w-xl text-lg text-slate-600">
        Adaptive AI Technical Interview Agent.
      </p>
      <Link
        to="/candidates"
        className="rounded-lg bg-brand px-6 py-3 font-medium text-white transition hover:bg-brand-dark"
      >
        Start an interview
      </Link>
    </section>
  );
}
