interface PageHeaderProps {
  title: string;
  subtext?: string;
  actions?: React.ReactNode;
}

export function PageHeader({ title, subtext, actions }: PageHeaderProps) {
  return (
    <header className="animate-fade-up mb-6 flex items-center justify-between gap-4 border-b border-zinc-200/80 pb-4 dark:border-zinc-800/80">
      <div className="min-w-0">
        <h1 className="truncate text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
          {title}
        </h1>
        {subtext && (
          <p className="mt-1 text-[15px] leading-relaxed text-zinc-500 dark:text-zinc-400">{subtext}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}
