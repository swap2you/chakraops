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
        "animate-fade-in rounded-xl border border-dashed border-zinc-300 bg-zinc-50/50 p-8 text-center",
        "dark:border-zinc-700/80 dark:bg-zinc-900/30",
        className
      )}
      role="region"
      aria-label="Empty state"
    >
      <h2 className="text-sm font-semibold text-zinc-600 dark:text-zinc-300">
        {title}
      </h2>
      {text ? (
        <p className="mx-auto mt-1.5 max-w-md text-xs leading-relaxed text-zinc-500 dark:text-zinc-500">{text}</p>
      ) : null}
      {action != null && <div className="mt-4 flex justify-center">{action}</div>}
    </section>
  );
}
