import { useState } from "react";
import { clsx } from "clsx";

interface TooltipProps {
  children: React.ReactNode;
  content?: string | null;
  className?: string;
}

export function Tooltip({ children, content, className }: TooltipProps) {
  const [show, setShow] = useState(false);
  return (
    <span
      className={clsx("relative inline-flex", className)}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
    >
      {children}
      {show && content && (
        <span
          className={clsx(
            "animate-scale-in absolute bottom-full left-1/2 z-50 mb-1.5 -translate-x-1/2 whitespace-nowrap",
            "rounded-lg border border-zinc-200/20 bg-zinc-900/95 px-2.5 py-1.5 text-xs text-zinc-100 shadow-lift backdrop-blur-sm",
            "dark:border-zinc-700/80 dark:bg-zinc-800/95 dark:text-zinc-200"
          )}
          role="tooltip"
        >
          {content}
        </span>
      )}
    </span>
  );
}
