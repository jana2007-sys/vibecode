/** Reusable button with optional link support and loading state. */

import {
  type ButtonHTMLAttributes,
  forwardRef,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";
import { RefreshIcon } from "./Icons";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  to?: string;
  loading?: boolean;
  fullWidth?: boolean;
  children: ReactNode;
}

const baseClasses =
  "inline-flex select-none items-center justify-center gap-2 rounded-xl font-semibold " +
  "transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950 disabled:cursor-not-allowed disabled:opacity-50";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-gradient-to-r from-indigo-500 via-violet-500 to-indigo-500 text-white " +
    "shadow-lg shadow-indigo-500/25 hover:shadow-glow hover:brightness-110 active:scale-[0.98]",
  secondary:
    "border border-white/10 bg-white/5 text-slate-100 hover:border-white/20 hover:bg-white/10 active:scale-[0.98]",
  ghost: "text-slate-300 hover:bg-white/5 hover:text-white",
  danger:
    "border border-rose-500/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20",
};

const sizeClasses: Record<Size, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2.5 text-sm",
  lg: "px-6 py-3 text-base",
};

function classes(variant: Variant, size: Size, fullWidth?: boolean, className?: string) {
  return [
    baseClasses,
    variantClasses[variant],
    sizeClasses[size],
    fullWidth ? "w-full" : "",
    className ?? "",
  ].join(" ");
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "primary",
      size = "md",
      to,
      loading = false,
      fullWidth = false,
      disabled,
      className,
      children,
      ...rest
    },
    ref
  ) {
    const cls = classes(variant, size, fullWidth, className);

    if (to) {
      // Hash links (e.g. "#how-it-works") must render as a real anchor so the
      // browser performs the smooth in-page scroll; react-router's Link cannot
      // navigate to a fragment on the current route.
      if (to.startsWith("#")) {
        return (
          <a href={to} className={cls} aria-disabled={disabled || loading}>
            {children}
          </a>
        );
      }
      return (
        <Link to={to} className={cls} aria-disabled={disabled || loading}>
          {children}
        </Link>
      );
    }

    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cls}
        {...rest}
      >
        {loading ? (
          <RefreshIcon className="h-4 w-4 animate-spin" />
        ) : null}
        {children}
      </button>
    );
  }
);
