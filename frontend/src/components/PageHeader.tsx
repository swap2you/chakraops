interface PageHeaderProps {
  title: string;
  subtext?: string;
  actions?: React.ReactNode;
}

export function PageHeader({ title, subtext, actions }: PageHeaderProps) {
  return (
    <header className="mb-4 flex items-center justify-between border-b border-zinc-800 pb-2">
      <div>
        <h1 className="text-lg font-semibold text-zinc-100">{title}</h1>
        {subtext && <p className="text-sm text-zinc-500">{subtext}</p>}
      </div>
      {actions}
    </header>
  );
}
