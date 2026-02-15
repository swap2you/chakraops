interface StatusBadgeProps {
  status: string;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const s = (status || "").toUpperCase();
  const color =
    s === "OK" || s === "PASS"
      ? "bg-emerald-500/20 text-emerald-400"
      : s === "WARN" || s === "FAIL"
        ? "bg-amber-500/20 text-amber-400"
        : s === "DOWN" || s === "BLOCKED"
          ? "bg-red-500/20 text-red-400"
          : "bg-zinc-500/20 text-zinc-400";
  return (
    <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>
      {status || "—"}
    </span>
  );
}
