import { clsx } from "clsx";

interface StatCardProps {
  label: string;
  value: React.ReactNode;
  badge?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}

export function StatCard(props: StatCardProps) {
  const { label, value, badge, icon, className } = props;
  return (
    <div
      className={clsx(
        "group animate-fade-up rounded-xl border border-zinc-200/80 bg-white p-4 shadow-soft",
        "transition-all duration-200 ease-out hover:-translate-y-0.5 hover:shadow-lift",
        // Solid dark background (see Card.tsx): translucent gradient over bg-white
        // made dark-mode cards unreadable.
        "dark:border-zinc-800/80 dark:bg-zinc-900/50 dark:shadow-none",
        "hover:border-emerald-500/30 dark:hover:border-emerald-400/25",
        className
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className="block text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
            {label}
          </span>
          <p className="mt-1 truncate font-mono text-xl font-semibold tabular-nums text-zinc-900 transition-colors group-hover:text-emerald-700 dark:text-zinc-100 dark:group-hover:text-emerald-300">
            {value}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {icon}
          {badge}
        </div>
      </div>
    </div>
  );
}
