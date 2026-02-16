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
        "rounded-lg border border-zinc-200 bg-white p-5 shadow-sm transition-all duration-200 ease-out dark:border-zinc-800 dark:bg-zinc-900/60 dark:shadow-none",
        "hover:border-zinc-300 hover:shadow-md dark:hover:border-zinc-700 dark:hover:shadow-lg dark:hover:shadow-black/20",
        className
      )}
    >
      {children}
    </section>
  );
}

export function CardHeader({ title, description, actions, children, className }: CardHeaderProps) {
  return (
    <div className={clsx("mb-3", className)}>
      {(title || description || actions) && (
        <div className="flex items-start justify-between gap-2">
          <div>
            {title && (
              <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-600 dark:text-zinc-500">
                {title}
              </h3>
            )}
            {description && (
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{description}</p>
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
