/** Top-level navigation bar.

Clean and minimal. On the interview screen it collapses to a slim strip so the
conversation keeps as much vertical space as possible.
*/

import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useInterviewContext } from "../context/InterviewContext";
import { useTheme } from "../hooks/useTheme";
import { Button } from "./ui/Button";
import {
  ChartIcon,
  CloseIcon,
  HistoryIcon,
  HomeIcon,
  MenuIcon,
  MoonIcon,
  SparklesIcon,
  SunIcon,
  UsersIcon,
} from "./ui/Icons";

const navItems = [
  { to: "/", label: "Home", icon: HomeIcon },
  { to: "/candidates", label: "Candidates", icon: UsersIcon },
  { to: "/history", label: "History", icon: HistoryIcon },
  { to: "/report", label: "Report", icon: ChartIcon },
];

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link
      to="/"
      className="flex items-center gap-2.5 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/70"
      aria-label="InterVue AI — home"
    >
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-teal-500 to-cyan-500 text-white shadow-lg shadow-teal-500/30 ring-1 ring-inset ring-white/20">
        <SparklesIcon className="h-4 w-4" />
      </span>
      {!compact ? (
        <span className="text-[15px] font-bold tracking-tight text-slate-900 dark:text-white">
          InterVue <span className="text-gradient">AI</span>
        </span>
      ) : null}
    </Link>
  );
}

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-teal-400/30 bg-white/5 text-slate-500 transition-all duration-200 hover:border-teal-400/60 hover:text-teal-600 hover:shadow-glow-cyan focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/70 dark:text-cyan-200 dark:hover:text-cyan-300"
    >
      {isDark ? (
        <SunIcon className="h-4 w-4" />
      ) : (
        <MoonIcon className="h-4 w-4" />
      )}
    </button>
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
      "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/70",
      isActive
        ? "bg-teal-500/10 text-slate-900 shadow-[inset_0_0_0_1px_rgba(20,184,166,0.35),0_0_20px_-8px_rgba(20,184,166,0.35)] dark:bg-teal-500/[0.08] dark:text-white dark:shadow-[inset_0_0_0_1px_rgba(20,184,166,0.35),0_0_20px_-8px_rgba(20,184,166,0.4)]"
        : "text-slate-500 hover:bg-teal-500/5 hover:text-teal-600 hover:shadow-[0_0_20px_-8px_rgba(20,184,166,0.3)] dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-cyan-300 dark:hover:shadow-[0_0_20px_-8px_rgba(6,182,212,0.35)]",
    ].join(" ");

  // Slim strip on the interview screen to preserve vertical space.
  if (isInterview) {
    return (
      <header className="nav-glass relative z-30">
        <nav className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4 sm:px-6">
          <Logo compact />
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <button
              type="button"
              onClick={endSession}
              className="rounded-lg px-2 py-1 text-sm font-medium text-slate-500 transition-colors hover:text-teal-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/70 dark:text-slate-400 dark:hover:text-cyan-300"
            >
              End session
            </button>
          </div>
        </nav>
      </header>
    );
  }

  return (
    <header className="nav-glass sticky top-0 z-30">
      <nav className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Logo />

        <div className="hidden items-center gap-1 md:flex">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} className={linkClass}>
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
          <div className="ml-3 flex items-center gap-2">
            <ThemeToggle />
            <Button to="/candidates" size="sm">
              Start Interview
            </Button>
          </div>
        </div>

        <div className="flex items-center gap-2 md:hidden">
          <ThemeToggle />
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-slate-600 transition-colors hover:bg-teal-500/5 hover:text-teal-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/70 dark:text-slate-300 dark:hover:bg-white/5 dark:hover:text-white"
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
        </div>
      </nav>

      {open ? (
        <div
          id="mobile-nav"
          className="border-t border-slate-200/70 px-4 pb-4 pt-2 md:hidden dark:border-white/5"
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
