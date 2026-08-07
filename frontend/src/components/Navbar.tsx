/** Top-level navigation bar. */

import { Link, NavLink } from "react-router-dom";

const navItems = [
  { to: "/", label: "Home" },
  { to: "/candidates", label: "Candidates" },
  { to: "/interview", label: "Interview" },
  { to: "/report", label: "Report" },
];

export function Navbar() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <Link to="/" className="text-lg font-semibold text-brand">
          InterVue AI
        </Link>
        <ul className="flex items-center gap-6">
          {navItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  isActive
                    ? "font-medium text-brand"
                    : "text-slate-600 hover:text-slate-900"
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
