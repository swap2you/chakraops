/**
 * R25.6: Universe Admin — current list, propose add/remove, apply, history. Safe labels only.
 */
import { useState } from "react";
import {
  useUniverseAdmin,
  useUniverseProposeAdd,
  useUniverseProposeRemove,
  useUniverseApply,
} from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, Table, TableHeader, TableBody, TableRow, TableHead, TableCell, Button } from "@/components/ui";
import { Loader2 } from "lucide-react";

function formatTs(iso: string): string {
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export function UniverseAdminPage() {
  const [search, setSearch] = useState("");
  const [addSymbol, setAddSymbol] = useState("");
  const [removeSymbol, setRemoveSymbol] = useState("");
  const [notes] = useState("");

  const { data, isLoading, isError, error } = useUniverseAdmin({ limit: 50 });
  const proposeAdd = useUniverseProposeAdd();
  const proposeRemove = useUniverseProposeRemove();
  const apply = useUniverseApply();

  const symbols = data?.symbols ?? [];
  const history = data?.history ?? [];
  const filtered = search.trim()
    ? symbols.filter((s) => s.toUpperCase().includes(search.trim().toUpperCase()))
    : symbols;
  const handleProposeAdd = () => {
    const sym = addSymbol.trim().toUpperCase();
    if (!sym) return;
    proposeAdd.mutate({ symbol: sym, notes: notes.trim() || undefined }, { onSuccess: () => setAddSymbol("") });
  };
  const handleProposeRemove = () => {
    const sym = removeSymbol.trim().toUpperCase();
    if (!sym) return;
    proposeRemove.mutate({ symbol: sym, notes: notes.trim() || undefined }, { onSuccess: () => setRemoveSymbol("") });
  };
  const handleApply = (proposalId: string) => {
    apply.mutate({ proposal_id: proposalId });
  };

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Universe Admin"
        subtext="Propose add/remove symbols and apply changes. History is logged."
      />

      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200">
          {error instanceof Error ? error.message : "Unable to load universe admin."}
        </div>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-zinc-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading…
        </div>
      )}

      {!isLoading && !isError && data && (
        <>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Propose Add
              </CardHeader>
              <div className="flex flex-wrap items-end gap-2">
                <div>
                  <label className="block text-xs text-zinc-500">Symbol</label>
                  <input
                    type="text"
                    value={addSymbol}
                    onChange={(e) => setAddSymbol(e.target.value)}
                    placeholder="TICK"
                    className="mt-1 w-24 rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>
                <Button size="sm" onClick={handleProposeAdd} disabled={proposeAdd.isPending || !addSymbol.trim()}>
                  {proposeAdd.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Propose Add"}
                </Button>
              </div>
            </Card>
            <Card>
              <CardHeader className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Propose Remove
              </CardHeader>
              <div className="flex flex-wrap items-end gap-2">
                <div>
                  <label className="block text-xs text-zinc-500">Symbol</label>
                  <input
                    type="text"
                    value={removeSymbol}
                    onChange={(e) => setRemoveSymbol(e.target.value)}
                    placeholder="TICK"
                    className="mt-1 w-24 rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>
                <Button size="sm" variant="secondary" onClick={handleProposeRemove} disabled={proposeRemove.isPending || !removeSymbol.trim()}>
                  {proposeRemove.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Propose Remove"}
                </Button>
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Current universe ({data.base_count} base, +{data.overlay_added_count} added, −{data.overlay_removed_count} removed) — {symbols.length} total
            </CardHeader>
            <div className="flex gap-2 pb-2">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search symbols…"
                className="w-48 rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
            <div className="max-h-60 overflow-auto rounded border border-zinc-200 dark:border-zinc-700">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.length === 0 ? (
                    <TableRow>
                      <TableCell className="text-zinc-500">No symbols match.</TableCell>
                    </TableRow>
                  ) : (
                    filtered.slice(0, 100).map((s) => (
                      <TableRow key={s}>
                        <TableCell className="font-medium">{s}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
            {filtered.length > 100 && <p className="mt-1 text-xs text-zinc-500">Showing first 100. Refine search to see more.</p>}
          </Card>

          <Card>
            <CardHeader className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              History (recent) — Open proposals can be applied
            </CardHeader>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Action</TableHead>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Apply</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {history.length === 0 ? (
                    <TableRow>
                      <td colSpan={5} className="py-3 pr-2 text-zinc-500">No history yet.</td>
                    </TableRow>
                  ) : (
                    history.map((h) => (
                      <TableRow key={h.id}>
                        <TableCell>{formatTs(h.ts)}</TableCell>
                        <TableCell>{h.action}</TableCell>
                        <TableCell className="font-medium">{h.symbol}</TableCell>
                        <TableCell>{h.status}</TableCell>
                        <TableCell>
                          {h.status === "OPEN" && (h.action === "PROPOSE_ADD" || h.action === "PROPOSE_REMOVE") && (
                            <Button size="sm" variant="outline" onClick={() => handleApply(h.id)} disabled={apply.isPending}>
                              Apply
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
