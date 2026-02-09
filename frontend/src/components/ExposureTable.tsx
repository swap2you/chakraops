/**
 * Phase 3: Reusable exposure table — by symbol or sector.
 */
import { Link } from "react-router-dom";
import type { ExposureItem } from "@/types/portfolio";
import { cn } from "@/lib/utils";

function formatCurrency(val: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

function formatPct(val: number): string {
  return `${(val * 100).toFixed(2)}%`;
}

interface ExposureTableProps {
  items: ExposureItem[];
  groupBy: "symbol" | "sector";
  sortKey?: "key" | "required_capital" | "pct_of_total_equity" | "position_count";
  sortDir?: "asc" | "desc";
  className?: string;
}

export function ExposureTable({
  items,
  groupBy,
  sortKey = "required_capital",
  sortDir = "desc",
  className,
}: ExposureTableProps) {
  const sorted = [...items].sort((a, b) => {
    const av = a[sortKey as keyof ExposureItem];
    const bv = b[sortKey as keyof ExposureItem];
    if (typeof av === "number" && typeof bv === "number") {
      return sortDir === "desc" ? (bv as number) - (av as number) : (av as number) - (bv as number);
    }
    const as = String(av ?? "");
    const bs = String(bv ?? "");
    return sortDir === "desc" ? bs.localeCompare(as) : as.localeCompare(bs);
  });

  const label = groupBy === "symbol" ? "Symbol" : "Sector";

  return (
    <div className={cn("overflow-x-auto rounded-lg border border-border", className)}>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/30 text-left text-muted-foreground">
            <th className="p-3 font-medium">{label}</th>
            <th className="p-3 font-medium">Required Capital</th>
            <th className="p-3 font-medium">% of Equity</th>
            <th className="p-3 font-medium">% of Available</th>
            <th className="p-3 font-medium">Positions</th>
            {groupBy === "symbol" ? <th className="p-3 font-medium">Link</th> : null}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={groupBy === "symbol" ? 6 : 5} className="p-6 text-center text-muted-foreground">
                No exposure data
              </td>
            </tr>
          ) : (
            sorted.map((row) => (
              <tr key={row.key} className="border-b border-border transition-colors hover:bg-muted/50">
                <td className="p-3 font-medium">{row.key}</td>
                <td className="p-3 tabular-nums">{formatCurrency(row.required_capital)}</td>
                <td className="p-3 tabular-nums">{formatPct(row.pct_of_total_equity)}</td>
                <td className="p-3 tabular-nums">{formatPct(row.pct_of_available_capital)}</td>
                <td className="p-3">{row.position_count}</td>
                {groupBy === "symbol" ? (
                  <td className="p-3">
                    <Link to={`/analysis?symbol=${row.key}`} className="text-primary hover:underline text-xs">
                      Ticker
                    </Link>
                  </td>
                ) : null}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
