import { clsx } from "clsx";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        "animate-pulse rounded bg-zinc-200 dark:bg-zinc-700/50",
        className
      )}
      aria-hidden
    />
  );
}
