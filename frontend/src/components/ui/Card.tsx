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
        "rounded-lg border border-zinc-200 bg-white p-6 shadow-sm transition-colors duration-150 dark:border-zinc-800 dark:bg-zinc-900/60 dark:shadow-none",
        "hover:border-zinc-300 dark:hover:border-zinc-700",
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
              <h3 className="text-xl font-semibold text-zinc-700 dark:text-zinc-300">
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
