import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useUniverse, useDecision } from "@/api/queries";
import { mergeUniverseWithDecision, buildSymbolsFromDecision } from "@/lib/mergeUniverseDecision";
import { PageHeader } from "@/components/PageHeader";
import {
  Card,
  CardHeader,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Badge,
  StatusBadge,
  EmptyState,
} from "@/components/ui";

function fmtTs(s: string | null | undefined): string {
  if (!s) return "n/a";
  try {
    const d = new Date(s);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return String(s);
  }
}

type VerdictFilter = "all" | "ELIGIBLE" | "HOLD" | "BLOCKED" | "NOT_EVALUATED";

const VERDICT_FILTER_OPTIONS: VerdictFilter[] = ["all", "ELIGIBLE", "HOLD", "BLOCKED", "NOT_EVALUATED"];

export function UniversePage() {
  const navigate = useNavigate();
  const { data: universeData, isLoading: universeLoading, isError } = useUniverse();
  const { data: decision } = useDecision("LIVE");
  const [search, setSearch] = useState("");
  const [verdictFilter, setVerdictFilter] = useState<VerdictFilter>("all");

  const baseSymbols = universeData?.symbols ?? [];
  const symbols = useMemo(() => {
    if (baseSymbols.length > 0) {
      return mergeUniverseWithDecision(baseSymbols, decision);
    }
    return buildSymbolsFromDecision(decision);
  }, [baseSymbols, decision]);
  const source = universeData?.source ?? "n/a";
  const updated = universeData?.updated_at ?? decision?.metadata?.pipeline_timestamp ?? "n/a";

  const filtered = useMemo(() => {
    let list = symbols;
    if (verdictFilter !== "all") {
      list = list.filter((s) => (s.final_verdict ?? s.verdict ?? "").toUpperCase() === verdictFilter);
    }
    const q = search.trim().toUpperCase();
    if (q) {
      list = list.filter(
        (s) =>
          s.symbol.toUpperCase().includes(q) ||
          (s.primary_reason ?? "").toUpperCase().includes(q)
      );
    }
    return list;
  }, [symbols, verdictFilter, search]);

  const isLoading = universeLoading;
  if (isLoading) {
    return (
      <div>
        <PageHeader title="Universe" subtext="Evaluated symbols" />
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
        </Card>
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <PageHeader title="Universe" />
        <p className="text-red-500 dark:text-red-400">Failed to load universe.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <PageHeader title="Universe" subtext={`Source: ${source} · Updated ${fmtTs(updated)}`} />
      <Card>
        <CardHeader title="Filters" />
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="text"
            placeholder="Search symbol or reason…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-56 rounded border border-zinc-200 bg-white px-2 py-1.5 text-sm text-zinc-900 placeholder-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:placeholder-zinc-500"
          />
          <div className="flex gap-1">
            {VERDICT_FILTER_OPTIONS.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setVerdictFilter(f)}
                className={`rounded border px-2 py-1 text-xs font-medium ${
                  verdictFilter === f
                    ? "border-zinc-500 bg-zinc-200 text-zinc-900 dark:border-zinc-500 dark:bg-zinc-700 dark:text-zinc-100"
                    : "border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800"
                }`}
              >
                {f === "all" ? "All" : f}
              </button>
            ))}
          </div>
        </div>
      </Card>
      <Card>
        <CardHeader
          title="Symbols"
          description={`${filtered.length} of ${symbols.length} · Updated ${fmtTs(updated)}`}
        />
        {filtered.length === 0 ? (
          <EmptyState
            title="No symbols"
            message={symbols.length === 0 ? "Universe is empty." : "No symbols match the current filters."}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableHead>Symbol</TableHead>
              <TableHead>Verdict</TableHead>
              <TableHead>Score</TableHead>
              <TableHead>Band</TableHead>
              <TableHead>Stage</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>Freshness</TableHead>
              <TableHead>Strategy</TableHead>
              <TableHead>Primary reason</TableHead>
              <TableHead>Price</TableHead>
              <TableHead>Expiration</TableHead>
            </TableHeader>
            <TableBody>
              {filtered.map((row) => (
                <TableRow
                  key={row.symbol}
                  onClick={() => navigate(`/symbol-diagnostics?symbol=${encodeURIComponent(row.symbol)}`)}
                >
                  <TableCell>
                    <span className="font-mono font-medium text-zinc-900 dark:text-zinc-200">{row.symbol}</span>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={row.final_verdict ?? row.verdict ?? "n/a"} />
                  </TableCell>
                  <TableCell numeric>
                    {row.score != null ? String(row.score) : "n/a"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={row.band === "A" ? "success" : row.band === "B" ? "warning" : "neutral"}>
                      {row.band ?? "n/a"}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-zinc-600 dark:text-zinc-400">
                    {row.stage_status ?? "n/a"}
                  </TableCell>
                  <TableCell className="font-mono text-zinc-600 dark:text-zinc-400">
                    {row.provider_status ?? "n/a"}
                  </TableCell>
                  <TableCell className="font-mono text-zinc-600 dark:text-zinc-400">
                    {row.data_freshness ? fmtTs(row.data_freshness) : "n/a"}
                  </TableCell>
                  <TableCell className="font-mono text-zinc-600 dark:text-zinc-400">
                    {row.strategy ?? "n/a"}
                  </TableCell>
                  <TableCell className="max-w-xs truncate text-zinc-600 dark:text-zinc-400" title={row.primary_reason ?? ""}>
                    {row.primary_reason ?? "n/a"}
                  </TableCell>
                  <TableCell numeric>
                    {row.price != null ? String(row.price) : "n/a"}
                  </TableCell>
                  <TableCell className="font-mono text-zinc-600 dark:text-zinc-400">
                    {row.expiration ?? "n/a"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}
