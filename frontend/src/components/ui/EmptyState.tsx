import { clsx } from "clsx";

interface EmptyStateProps {
  title: string;
  message?: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ title, message, description, action, className }: EmptyStateProps) {
  const text = message ?? description ?? "";
  return (
    <section
      className={clsx(
        "rounded-lg border border-zinc-800 bg-zinc-900/30 p-6 text-center dark:border-zinc-800 dark:bg-zinc-900/30 light:border-zinc-200 light:bg-zinc-50",
        className
      )}
      role="region"
      aria-label="Empty state"
    >
      <h2 className="text-sm font-semibold text-zinc-400 dark:text-zinc-400 light:text-zinc-600">
        {title}
      </h2>
      {text ? <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-500 light:text-zinc-500">{text}</p> : null}
      {action != null && <div className="mt-3">{action}</div>}
    </section>
  );
}
