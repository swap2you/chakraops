import { clsx } from "clsx";

interface CardProps {
  children: React.ReactNode;
  className?: string;
}

interface CardHeaderProps {
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}

export function Card({ children, className }: CardProps) {
  return (
    <section
      className={clsx(
        "rounded-lg border border-zinc-200 bg-white p-3 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/50 dark:shadow-none",
        className
      )}
    >
      {children}
    </section>
  );
}

export function CardHeader({ title, description, actions, children, className }: CardHeaderProps) {
  return (
    <div className={clsx("mb-2", className)}>
      {(title || description || actions) && (
        <div className="flex items-start justify-between gap-2">
          <div>
            {title && (
              <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-600 dark:text-zinc-500">
                {title}
              </h3>
            )}
            {description && (
              <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{description}</p>
            )}
          </div>
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}

export function CardBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={clsx("text-sm", className)}>{children}</div>;
}
