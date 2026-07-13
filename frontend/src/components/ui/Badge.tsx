import { clsx } from "clsx";

type BadgeVariant = "default" | "success" | "warning" | "danger" | "neutral";

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

const variantMap: Record<BadgeVariant, string> = {
  default:
    "ring-zinc-300/80 bg-zinc-100 text-zinc-700 dark:ring-zinc-600/60 dark:bg-zinc-800/60 dark:text-zinc-300",
  success:
    "ring-emerald-600/30 bg-emerald-50 text-emerald-700 dark:ring-emerald-400/30 dark:bg-emerald-500/10 dark:text-emerald-400",
  warning:
    "ring-amber-600/30 bg-amber-50 text-amber-700 dark:ring-amber-400/30 dark:bg-amber-500/10 dark:text-amber-400",
  danger:
    "ring-red-600/30 bg-red-50 text-red-700 dark:ring-red-400/30 dark:bg-red-500/10 dark:text-red-400",
  neutral:
    "ring-zinc-400/50 bg-zinc-100 text-zinc-600 dark:ring-zinc-500/40 dark:bg-zinc-500/10 dark:text-zinc-400",
};

const dotMap: Record<BadgeVariant, string> = {
  default: "bg-zinc-400 dark:bg-zinc-500",
  success: "bg-emerald-500 dark:bg-emerald-400",
  warning: "bg-amber-500 dark:bg-amber-400",
  danger: "bg-red-500 dark:bg-red-400",
  neutral: "bg-zinc-400 dark:bg-zinc-500",
};

export function Badge({ children, variant = "default", className }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        "transition-colors duration-150",
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
  if (s === "OK" || s === "PASS" || s === "ELIGIBLE") v = "success";
  else if (s === "WARN" || s === "FAIL" || s === "HOLD") v = "warning";
  else if (s === "DOWN" || s === "BLOCKED" || s === "CRITICAL") v = "danger";
  const label = (() => {
    if (!status || !status.trim()) return "—";
    if (s === "PASS") return "Passed";
    if (s === "FAIL") return "Blocked";
    if (s === "WARN") return "Degraded";
    return status;
  })();
  return (
    <Badge variant={v}>
      <span className={clsx("h-1.5 w-1.5 shrink-0 rounded-full", dotMap[v])} aria-hidden />
      {label}
    </Badge>
  );
}
