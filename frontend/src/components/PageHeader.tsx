/**
 * Phase 8.6: Standard page header — title + one-line subtext + optional actions right.
 */
export interface PageHeaderProps {
  title: string;
  subtext: string;
  actions?: React.ReactNode;
}

export function PageHeader({ title, subtext, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtext}</p>
      </div>
      {actions != null && <div className="shrink-0">{actions}</div>}
    </div>
  );
}
