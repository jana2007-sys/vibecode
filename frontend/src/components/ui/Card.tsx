/** Reusable glassmorphism card surface. */

import { type HTMLAttributes } from "react";

export function Card({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`card-glass ${className ?? ""}`}
      {...rest}
    >
      {children}
    </div>
  );
}
