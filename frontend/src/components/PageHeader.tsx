interface PageHeaderProps {
  title: string;
  subtext?: string;
  actions?: React.ReactNode;
}

export function PageHeader({ title, subtext, actions }: PageHeaderProps) {
  return (
    <header className="mb-6 flex items-center justify-between border-b border-zinc-200 pb-4 dark:border-zinc-800">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">{title}</h1>
        {subtext && <p className="mt-1 text-[15px] text-zinc-500 dark:text-zinc-500">{subtext}</p>}
      </div>
      {actions}
    </header>
  );
}
