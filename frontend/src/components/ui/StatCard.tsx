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
        "rounded-lg border border-zinc-200 bg-white p-3 shadow-sm",
        "dark:border-zinc-800 dark:bg-zinc-900/50 dark:shadow-none",
        className
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <span className="block text-xs font-medium text-zinc-600 dark:text-zinc-500">
            {label}
          </span>
          <p className="mt-0.5 font-mono text-lg font-semibold text-zinc-900 dark:text-zinc-200">
            {value}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {icon}
          {badge}
        </div>
      </div>
    </div>
  );
}
