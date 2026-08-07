/** 404 page shell. */

import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <section className="flex flex-col items-center gap-4 py-16 text-center">
      <h2 className="text-3xl font-bold text-slate-900">Page not found</h2>
      <p className="text-slate-600">The page you are looking for does not exist.</p>
      <Link to="/" className="text-brand hover:underline">
        Back to home
      </Link>
    </section>
  );
}
