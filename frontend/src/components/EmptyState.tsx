/**
 * Phase 8.6: Standard empty state — title, one-line explanation, optional suggestion.
 */
export interface EmptyStateProps {
  title: string;
  message: string;
  /** Optional primary suggestion (e.g. link or button) */
  action?: React.ReactNode;
}

export function EmptyState({ title, message, action }: EmptyStateProps) {
  return (
    <section
      className="rounded-lg border border-border bg-card p-8 text-center"
      role="region"
      aria-label="Empty state"
    >
      <h2 className="text-lg font-medium text-foreground">{title}</h2>
      <p className="mt-2 text-sm text-muted-foreground">{message}</p>
      {action != null && <div className="mt-4">{action}</div>}
    </section>
  );
}
