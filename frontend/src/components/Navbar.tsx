/** Top-level navigation bar.

Clean and minimal. On the interview screen it collapses to a slim strip so the
conversation keeps as much vertical space as possible.
*/

import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useInterviewContext } from "../context/InterviewContext";
import { Button } from "./ui/Button";
import {
  ChartIcon,
  CloseIcon,
  HomeIcon,
  MenuIcon,
  SparklesIcon,
  UsersIcon,
} from "./ui/Icons";

const navItems = [
  { to: "/", label: "Home", icon: HomeIcon },
  { to: "/candidates", label: "Candidates", icon: UsersIcon },
  { to: "/report", label: "Report", icon: ChartIcon },
];

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link
      to="/"
      className="flex items-center gap-2.5 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70"
      aria-label="InterVue AI — home"
    >
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/30">
        <SparklesIcon className="h-4 w-4" />
      </span>
      {!compact ? (
        <span className="text-[15px] font-bold tracking-tight text-white">
          InterVue <span className="text-gradient">AI</span>
        </span>
      ) : null}
    </Link>
  );
}

export function Navbar() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { reset } = useInterviewContext();
  const isInterview = location.pathname === "/interview";

  const endSession = () => {
    reset();
    navigate("/candidates");
  };

  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    [
      "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70",
      isActive
        ? "text-white"
        : "text-slate-400 hover:bg-white/5 hover:text-white",
    ].join(" ");

  // Slim strip on the interview screen to preserve vertical space.
  if (isInterview) {
    return (
      <header className="relative z-30 border-b border-white/5 bg-ink-950/70 backdrop-blur-xl">
        <nav className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4 sm:px-6">
          <Logo compact />
          <button
            type="button"
            onClick={endSession}
            className="text-sm font-medium text-slate-400 transition-colors hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70 rounded-lg px-2 py-1"
          >
            End session
          </button>
        </nav>
      </header>
    );
  }

  return (
    <header className="sticky top-0 z-30 border-b border-white/5 bg-ink-950/70 backdrop-blur-xl">
      <nav className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Logo />

        <div className="hidden items-center gap-1 md:flex">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} className={linkClass}>
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
          <div className="ml-3">
            <Button to="/candidates" size="sm">
              Start Interview
            </Button>
          </div>
        </div>

        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-slate-300 transition-colors hover:bg-white/5 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70 md:hidden"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? "Close navigation" : "Open navigation"}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? (
            <CloseIcon className="h-5 w-5" />
          ) : (
            <MenuIcon className="h-5 w-5" />
          )}
        </button>
      </nav>

      {open ? (
        <div
          id="mobile-nav"
          className="border-t border-white/5 px-4 pb-4 pt-2 md:hidden"
        >
          <div className="flex flex-col gap-1">
            {navItems.map((item) => (
              <NavLink key={item.to} to={item.to} className={linkClass}>
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
            <Button to="/candidates" className="mt-2" fullWidth>
              Start Interview
            </Button>
          </div>
        </div>
      ) : null}
    </header>
  );
}
