import { clsx } from "clsx";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        "shimmer animate-pulse rounded-md bg-zinc-200/90 dark:bg-zinc-800/80",
        className
      )}
      aria-hidden
    />
  );
}
