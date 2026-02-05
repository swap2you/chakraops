/**
 * Phase 7.2 / 8.6: Alerts — dashboard shows ONLY actionable; uses central classifier.
 */
import type { AlertsView } from "@/types/views";
import { alertsForDashboard, severityBorderClass } from "@/lib/alertClassifier";
import { cn } from "@/lib/utils";

export interface AlertsSectionProps {
  alerts: AlertsView | null;
}

export function AlertsSection({ alerts }: AlertsSectionProps) {
  const items = alerts?.items ?? [];
  const actionable = alertsForDashboard(items);
  if (actionable.length === 0) return null;

  return (
    <section
      className="rounded-lg border border-border bg-card p-4"
      role="region"
      aria-label="Alerts"
    >
      <h2 className="text-sm font-medium text-muted-foreground">Alerts</h2>
      <ul className="mt-3 space-y-2">
        {actionable.map((item, i) => (
          <li
            key={i}
            className={cn(
              "rounded-md border border-transparent px-3 py-2 text-sm",
              severityBorderClass(item.level)
            )}
          >
            <span className="font-medium text-foreground">
              {item.symbol ? `${item.symbol} — ` : ""}
              {item.code ?? "Alert"}
            </span>{" "}
            <span className="text-muted-foreground">
              {item.message ?? ""}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
