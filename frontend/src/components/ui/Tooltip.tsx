import { useState } from "react";
import { clsx } from "clsx";

interface TooltipProps {
  children: React.ReactNode;
  content: string;
  className?: string;
}

export function Tooltip({ children, content, className }: TooltipProps) {
  const [show, setShow] = useState(false);
  return (
    <span
      className={clsx("relative inline-flex", className)}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && content && (
        <span
          className="absolute bottom-full left-1/2 z-50 mb-1 -translate-x-1/2 rounded border border-zinc-200 bg-zinc-800 px-2 py-1 text-xs text-zinc-100 shadow-lg whitespace-nowrap dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
          role="tooltip"
        >
          {content}
        </span>
      )}
    </span>
  );
}
