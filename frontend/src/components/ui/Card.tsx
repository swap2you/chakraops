import { clsx } from "clsx";

interface CardProps extends React.HTMLAttributes<HTMLElement> {
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

export function Card({ children, className, ...rest }: CardProps) {
  return (
    <section
      className={clsx(
        "animate-fade-up rounded-xl border border-zinc-200/80 bg-white p-6 shadow-soft",
        "transition-all duration-200 ease-out",
        "hover:-translate-y-0.5 hover:border-zinc-300 hover:shadow-lift",
        // Dark mode needs a SOLID background-color: gradient utilities only set the
        // background-image, and a translucent gradient over the light-mode bg-white
        // washes the card out and kills text contrast.
        "dark:border-zinc-800/80 dark:bg-zinc-900/60 dark:shadow-none",
        "dark:hover:border-zinc-700",
        className
      )}
      {...rest}
    >
      {children}
    </section>
  );
}

export function CardHeader({ title, description, actions, children, className }: CardHeaderProps) {
  return (
    <div className={clsx("mb-4", className)}>
      {(title || description || actions) && (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && (
              <h3 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
                {title}
              </h3>
            )}
            {description && (
              <p className="mt-1 text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">{description}</p>
            )}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

export function CardBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={clsx("text-sm", className)}>{children}</div>;
}
