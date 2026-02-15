import { clsx } from "clsx";

type BadgeVariant = "default" | "success" | "warning" | "danger" | "neutral";

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

const variantMap: Record<BadgeVariant, string> = {
  default:
    "border-zinc-300 bg-zinc-100 text-zinc-700 dark:border-zinc-600 dark:bg-zinc-800/50 dark:text-zinc-300",
  success:
    "border-emerald-600/50 bg-emerald-50 text-emerald-700 dark:border-emerald-500/50 dark:bg-emerald-500/10 dark:text-emerald-400",
  warning:
    "border-amber-600/50 bg-amber-50 text-amber-700 dark:border-amber-500/50 dark:bg-amber-500/10 dark:text-amber-400",
  danger:
    "border-red-600/50 bg-red-50 text-red-700 dark:border-red-500/50 dark:bg-red-500/10 dark:text-red-400",
  neutral:
    "border-zinc-400 bg-zinc-100 text-zinc-600 dark:border-zinc-500/50 dark:bg-zinc-500/10 dark:text-zinc-400",
};

export function Badge({ children, variant = "default", className }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex rounded border px-2 py-0.5 text-xs font-medium",
        variantMap[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const s = (status || "").toUpperCase();
  let v: BadgeVariant = "neutral";
  if (s === "OK" || s === "PASS") v = "success";
  else if (s === "WARN" || s === "FAIL") v = "warning";
  else if (s === "DOWN" || s === "BLOCKED") v = "danger";
  return <Badge variant={v}>{status || "—"}</Badge>;
}
