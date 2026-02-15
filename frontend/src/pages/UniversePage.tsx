import { useUniverse } from "@/api/queries";
import type { UniverseSymbol } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { DataTable } from "@/components/DataTable";
import { StatusBadge } from "@/components/StatusBadge";

export function UniversePage() {
  const { data, isLoading, isError } = useUniverse();

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Universe" />
        <p className="text-zinc-400">Loading…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <PageHeader title="Universe" />
        <p className="text-red-400">Failed to load universe.</p>
      </div>
    );
  }

  const symbols = data?.symbols ?? [];
  const source = data?.source ?? "—";
  const updated = data?.updated_at ?? "—";

  const columns = [
    {
      key: "symbol",
      header: "Symbol",
      render: (row: UniverseSymbol) => <span className="font-mono">{row.symbol}</span>,
    },
    {
      key: "verdict",
      header: "Verdict",
      render: (row: UniverseSymbol) => (
        <StatusBadge status={row.final_verdict ?? row.verdict ?? "—"} />
      ),
    },
    {
      key: "score",
      header: "Score",
      render: (row: UniverseSymbol) => (
        <span className="font-mono">{row.score != null ? row.score : "—"}</span>
      ),
    },
    {
      key: "band",
      header: "Band",
      render: (row: UniverseSymbol) => <span className="font-mono">{row.band ?? "—"}</span>,
    },
    {
      key: "primary_reason",
      header: "Primary Reason",
      render: (row: UniverseSymbol) => (
        <span className="max-w-xs truncate text-zinc-400">{row.primary_reason ?? "—"}</span>
      ),
    },
    {
      key: "price",
      header: "Price",
      render: (row: UniverseSymbol) => (
        <span className="font-mono">{row.price != null ? row.price : "—"}</span>
      ),
    },
    {
      key: "expiration",
      header: "Expiration",
      render: (row: UniverseSymbol) => <span className="font-mono">{row.expiration ?? "—"}</span>,
    },
  ];

  return (
    <div>
      <PageHeader title="Universe" />
      <div className="mb-4 flex gap-4 text-sm text-zinc-500">
        <span>source: {source}</span>
        <span>updated: {updated}</span>
      </div>
      <DataTable columns={columns} data={symbols} keyFn={(r) => r.symbol} />
      {symbols.length === 0 && <p className="mt-4 text-zinc-500">No symbols.</p>}
    </div>
  );
}
