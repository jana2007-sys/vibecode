/** Reusable glassmorphism card surface. */

import { type HTMLAttributes } from "react";

export function Card({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-2xl border border-white/10 bg-white/[0.04] shadow-xl shadow-black/20 backdrop-blur-xl ${className ?? ""}`}
      {...rest}
    >
      {children}
    </div>
  );
}
