/**
 * R25.5: Trade journal — SQLite-backed manual executions.
 * Uses /api/ui/journal (GET/POST/PATCH) and export. Safe labels only.
 */
import { useState, useMemo } from "react";
import {
  useJournal,
  useJournalCreate,
  useJournalUpdate,
  useJournalExport,
  downloadJournalReadinessPack,
  downloadJournalReadinessPacksJsonl,
  useJournalEntryReadinessPack,
} from "@/api/queries";
import type { JournalEntry } from "@/api/queries";
import { safeForReadinessDisplay } from "@/utils/sanitizeDisplay";
import { PageHeader } from "@/components/PageHeader";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  EmptyState,
  Button,
  Badge,
} from "@/components/ui";
import { Link } from "react-router-dom";
import { Plus, Download, Loader2, Pencil, Check, X } from "lucide-react";

function formatCurrency(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(val);
}

function formatDate(s: string): string {
  if (!s) return "—";
  try {
    const d = new Date(s);
    return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString(undefined, { dateStyle: "short" });
  } catch {
    return s;
  }
}

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function monthToRange(month: string): { from_date: string; to_date: string } {
  const [y, m] = month.split("-").map(Number);
  const from_date = `${month}-01`;
  const last = new Date(y, m, 0).getDate();
  const to_date = `${month}-${String(last).padStart(2, "0")}`;
  return { from_date, to_date };
}

const STRATEGIES = ["", "SHARES", "CSP", "CC"] as const;
const ACTIONS = ["BUY", "SELL", "OPEN_CSP", "CLOSE_CSP", "OPEN_CC", "CLOSE_CC", "ROLL"] as const;

export function JournalPage() {
  const [month, setMonth] = useState(currentMonth());
  const [symbolFilter, setSymbolFilter] = useState("");
  const [strategyFilter, setStrategyFilter] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editNotes, setEditNotes] = useState("");
  const [editTags, setEditTags] = useState("");
  const [includePaper, setIncludePaper] = useState(false);
  const [paperOnly, setPaperOnly] = useState(false);
  const [hasPackFilter, setHasPackFilter] = useState(true);
  const [viewPackEntryId, setViewPackEntryId] = useState<string | null>(null);
  const [downloadingPacks, setDownloadingPacks] = useState(false);

  const { from_date, to_date } = useMemo(() => monthToRange(month), [month]);
  const { data, isLoading, isError, error } = useJournal({
    from_date,
    to_date,
    symbol: symbolFilter.trim() || undefined,
    strategy: strategyFilter.trim() || undefined,
    limit: 200,
    include_paper: paperOnly ? true : includePaper,
    paper_only: paperOnly,
  });
  const createMutation = useJournalCreate();
  const updateMutation = useJournalUpdate();
  const exportMutation = useJournalExport();

  const allEntries = data?.entries ?? [];
  const entries = hasPackFilter ? allEntries.filter((e) => e.has_readiness_pack) : allEntries;

  const handleExport = async () => {
    try {
      const csv = await exportMutation.mutateAsync({ from_date, to_date });
      const blob = new Blob([csv], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `journal_${from_date}_${to_date}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      // Error surfaced by mutation
    }
  };

  const startEdit = (e: JournalEntry) => {
    setEditingId(e.id);
    setEditNotes(e.notes ?? "");
    setEditTags(e.tags ?? "");
  };
  const cancelEdit = () => {
    setEditingId(null);
    setEditNotes("");
    setEditTags("");
  };
  const saveEdit = async () => {
    if (!editingId) return;
    try {
      await updateMutation.mutateAsync({
        id: editingId,
        payload: { notes: editNotes || null, tags: editTags || null },
      });
      cancelEdit();
    } catch {
      // Error surfaced by mutation
    }
  };

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Journal"
        subtext="Canonical fill record for manual executions (shares and options). Export to CSV."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
              disabled={exportMutation.isPending || entries.length === 0}
            >
              {exportMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              Export CSV
            </Button>
            <Button
              variant="outline"
              size="sm"
              data-testid="journal-download-readiness-packs"
              disabled={downloadingPacks}
              onClick={async () => {
                setDownloadingPacks(true);
                try {
                  await downloadJournalReadinessPacksJsonl({
                    has_pack: hasPackFilter,
                    from_date,
                    to_date,
                    limit: 200,
                  });
                } finally {
                  setDownloadingPacks(false);
                }
              }}
            >
              {downloadingPacks ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Download readiness packs (JSONL)
            </Button>
            <Button size="sm" onClick={() => setAddOpen(true)}>
              <Plus className="h-4 w-4" />
              Add entry
            </Button>
          </div>
        }
      />

      <div
        className="rounded border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900/40 dark:text-zinc-300"
        data-testid="journal-canonical-banner"
      >
        Journal is the canonical fill record for manual executions. Paper and live fills may both appear here when included; Portfolio is separate.
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
          Month
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value || currentMonth())}
            className="rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
          Symbol
          <input
            type="text"
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
            placeholder="e.g. SPY"
            className="w-24 rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400" data-testid="journal-include-paper">
          <input
            type="checkbox"
            checked={includePaper}
            onChange={(e) => setIncludePaper(e.target.checked)}
            className="rounded border-zinc-300 dark:border-zinc-600"
          />
          Include paper
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400" data-testid="journal-paper-only">
          <input
            type="checkbox"
            checked={paperOnly}
            onChange={(e) => setPaperOnly(e.target.checked)}
            className="rounded border-zinc-300 dark:border-zinc-600"
          />
          Paper only
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400" data-testid="journal-filter-has-pack">
          <input
            type="checkbox"
            checked={hasPackFilter}
            onChange={(e) => setHasPackFilter(e.target.checked)}
            className="rounded border-zinc-300 dark:border-zinc-600"
          />
          Has readiness pack
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
          Strategy
          <select
            value={strategyFilter}
            onChange={(e) => setStrategyFilter(e.target.value)}
            className="rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
          >
            <option value="">All</option>
            {STRATEGIES.filter(Boolean).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>

      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200">
          {error instanceof Error ? error.message : "Unable to load journal."}
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50/50 p-12 text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900/50">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading…
        </div>
      )}

      {!isLoading && !isError && entries.length === 0 && (
        <EmptyState
          title="No entries this month"
          message="Add an entry to record a manual trade (shares or options)."
        />
      )}

      {!isLoading && !isError && entries.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <Table>
            <TableHeader>
                <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead>Strategy</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Paper</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Price</TableHead>
                <TableHead className="text-right">Premium</TableHead>
                <TableHead className="text-right">Fees</TableHead>
                <TableHead className="text-right">Realized P/L</TableHead>
                <TableHead>Notes</TableHead>
                <TableHead>Tags</TableHead>
                <TableHead className="w-20">Open</TableHead>
                <TableHead className="w-20">Edit</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((e) => {
                const linkTarget = e.link_target;
                const openUrl =
                  linkTarget?.kind === "shares" && linkTarget?.id
                    ? `/symbol-diagnostics?symbol=${encodeURIComponent(linkTarget.id.split(":")[0])}`
                    : linkTarget
                      ? "/portfolio"
                      : null;
                return (
                <TableRow key={e.id}>
                  <TableCell>{formatDate(e.trade_date)}</TableCell>
                  <TableCell className="font-medium">{e.symbol}</TableCell>
                  <TableCell>{e.strategy}</TableCell>
                  <TableCell>{e.action}</TableCell>
                  <TableCell>{e.is_paper ? <Badge variant="neutral" data-testid="journal-paper-badge">Paper</Badge> : "—"}</TableCell>
                  <TableCell className="text-right">{e.qty}</TableCell>
                  <TableCell className="text-right">{e.price != null ? formatCurrency(e.price) : "—"}</TableCell>
                  <TableCell className="text-right">{e.premium != null ? formatCurrency(e.premium) : "—"}</TableCell>
                  <TableCell className="text-right">{e.fees != null ? formatCurrency(e.fees) : "—"}</TableCell>
                  <TableCell className={`text-right font-medium ${(e.realized_pl ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                    {e.realized_pl != null ? formatCurrency(e.realized_pl) : "—"}
                  </TableCell>
                  <TableCell className="max-w-[140px]">
                    {editingId === e.id ? (
                      <input
                        value={editNotes}
                        onChange={(ev) => setEditNotes(ev.target.value)}
                        className="w-full rounded border border-zinc-300 px-1.5 py-0.5 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                        placeholder="Notes"
                      />
                    ) : (
                      <span className="truncate text-zinc-600 dark:text-zinc-400">{e.notes ?? "—"}</span>
                    )}
                  </TableCell>
                  <TableCell className="max-w-[120px]">
                    {editingId === e.id ? (
                      <input
                        value={editTags}
                        onChange={(ev) => setEditTags(ev.target.value)}
                        className="w-full rounded border border-zinc-300 px-1.5 py-0.5 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                        placeholder="Tags"
                      />
                    ) : (
                      <span className="truncate text-zinc-600 dark:text-zinc-400">{e.tags ?? "—"}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {openUrl ? (
                      <Link to={openUrl} className="text-sm text-emerald-600 hover:underline dark:text-emerald-400" data-testid="journal-open-link">
                        Open
                      </Link>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell>
                    {e.has_readiness_pack ? (
                      <div className="flex flex-col gap-0.5">
                        <button
                          type="button"
                          onClick={() => setViewPackEntryId(e.id)}
                          className="text-sm text-blue-600 hover:underline dark:text-blue-400 text-left"
                          data-testid="journal-view-readiness-pack"
                        >
                          View readiness pack
                        </button>
                        <button
                          type="button"
                          onClick={() => void downloadJournalReadinessPack(e.id, e.symbol)}
                          className="text-sm text-blue-600 hover:underline dark:text-blue-400 text-left"
                          data-testid="journal-download-readiness-pack"
                        >
                          Download readiness pack
                        </button>
                      </div>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell>
                    {editingId === e.id ? (
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={saveEdit}
                          disabled={updateMutation.isPending}
                          className="rounded p-1 text-emerald-600 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-900/30"
                          aria-label="Save"
                        >
                          <Check className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={cancelEdit}
                          className="rounded p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                          aria-label="Cancel"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => startEdit(e)}
                        className="rounded p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                        aria-label="Edit notes and tags"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                    )}
                  </TableCell>
                </TableRow>
              );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {addOpen && (
        <AddEntryModal
          defaultDate={from_date}
          onClose={() => setAddOpen(false)}
          onAdded={() => {
            setAddOpen(false);
            createMutation.reset();
          }}
          onCreate={createMutation.mutateAsync}
          isPending={createMutation.isPending}
        />
      )}

      {viewPackEntryId && (
        <ReadinessPackModal
          entryId={viewPackEntryId}
          onClose={() => setViewPackEntryId(null)}
        />
      )}
    </div>
  );
}

function ReadinessPackModal({ entryId, onClose }: { entryId: string; onClose: () => void }) {
  const { data, isLoading, isError } = useJournalEntryReadinessPack(entryId, true);
  const readiness = data?.readiness;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="readiness-pack-title">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-900 shadow-xl">
        <div className="sticky top-0 flex items-center justify-between border-b border-zinc-200 bg-white px-4 py-3 dark:border-zinc-700 dark:bg-zinc-900">
          <h2 id="readiness-pack-title" className="text-lg font-semibold text-zinc-800 dark:text-zinc-100">Readiness pack</h2>
          <Button size="sm" variant="secondary" onClick={onClose}>Close</Button>
        </div>
        <div className="p-4 space-y-4 text-sm">
          {isLoading && <p className="text-zinc-600 dark:text-zinc-400">Loading…</p>}
          {isError && <p className="text-amber-600 dark:text-amber-400">Readiness pack not available.</p>}
          {!isLoading && !isError && readiness && (
            <>
              <section>
                <h3 className="font-medium text-zinc-800 dark:text-zinc-200 mb-1">Summary</h3>
                <p className="text-zinc-600 dark:text-zinc-400">
                  {safeForReadinessDisplay(readiness.status)} — {safeForReadinessDisplay(readiness.status_label)}
                  {readiness.as_of_utc != null && ` (${safeForReadinessDisplay(readiness.as_of_utc)})`}
                </p>
              </section>
              <section>
                <h3 className="font-medium text-zinc-800 dark:text-zinc-200 mb-2">Checks</h3>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr className="border-b border-zinc-200 dark:border-zinc-700">
                        <th className="py-1 pr-2 font-medium text-zinc-700 dark:text-zinc-300">Code</th>
                        <th className="py-1 pr-2 font-medium text-zinc-700 dark:text-zinc-300">Status</th>
                        <th className="py-1 pr-2 font-medium text-zinc-700 dark:text-zinc-300">Label</th>
                        <th className="py-1 pr-2 font-medium text-zinc-700 dark:text-zinc-300">Detail</th>
                        <th className="py-1 font-medium text-zinc-700 dark:text-zinc-300">Fix</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(readiness.checks ?? []).map((c, i) => (
                        <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800">
                          <td className="py-1 pr-2 text-zinc-700 dark:text-zinc-300">{safeForReadinessDisplay(c.code)}</td>
                          <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{safeForReadinessDisplay(c.status)}</td>
                          <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{safeForReadinessDisplay(c.label)}</td>
                          <td className="py-1 pr-2 text-zinc-500 dark:text-zinc-500">{safeForReadinessDisplay(c.detail)}</td>
                          <td className="py-1">
                            {c.action_href != null && c.action_href !== "" ? (
                              <Link to={c.action_href} className="text-blue-600 hover:underline dark:text-blue-400">Fix</Link>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section>
                <h3 className="font-medium text-zinc-800 dark:text-zinc-200 mb-1">Order stub</h3>
                <pre className="rounded bg-zinc-100 dark:bg-zinc-800 p-3 text-xs text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap overflow-x-auto">
                  {(readiness.order_stub?.lines ?? []).map((line) => safeForReadinessDisplay(line)).join("\n") || "—"}
                </pre>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function AddEntryModal({
  defaultDate,
  onClose,
  onAdded,
  onCreate,
  isPending,
}: {
  defaultDate: string;
  onClose: () => void;
  onAdded: () => void;
  onCreate: (p: Record<string, unknown>) => Promise<JournalEntry>;
  isPending: boolean;
}) {
  const [trade_date, setTradeDate] = useState(defaultDate);
  const [symbol, setSymbol] = useState("");
  const [strategy, setStrategy] = useState("SHARES");
  const [action, setAction] = useState("BUY");
  const [qty, setQty] = useState(1);
  const [price, setPrice] = useState("");
  const [premium, setPremium] = useState("");
  const [fees, setFees] = useState("");
  const [contract_key, setContractKey] = useState("");
  const [expiry, setExpiry] = useState("");
  const [strike, setStrike] = useState("");
  const [right, setRight] = useState("");
  const [notes, setNotes] = useState("");
  const [tags, setTags] = useState("");
  const [realized_pl, setRealizedPl] = useState("");
  const [link_id, setLinkId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const payload: Record<string, unknown> = {
      trade_date: trade_date.slice(0, 10),
      symbol: symbol.trim().toUpperCase(),
      strategy: strategy.trim().toUpperCase(),
      action: action.trim().toUpperCase(),
      qty: Number(qty) || 0,
    };
    if (price !== "") {
      const p = parseFloat(price);
      if (!Number.isNaN(p)) payload.price = p;
    }
    if (premium !== "") {
      const p = parseFloat(premium);
      if (!Number.isNaN(p)) payload.premium = p;
    }
    if (fees !== "") {
      const f = parseFloat(fees);
      if (!Number.isNaN(f)) payload.fees = f;
    }
    if (contract_key.trim()) payload.contract_key = contract_key.trim();
    if (expiry.trim()) payload.expiry = expiry.trim().slice(0, 10);
    if (strike !== "") {
      const s = parseFloat(strike);
      if (!Number.isNaN(s)) payload.strike = s;
    }
    if (right.trim()) payload.right = right.trim();
    if (notes.trim()) payload.notes = notes.trim();
    if (tags.trim()) payload.tags = tags.trim();
    if (realized_pl !== "") {
      const r = parseFloat(realized_pl);
      if (!Number.isNaN(r)) payload.realized_pl = r;
    }
    if (link_id.trim()) payload.link_id = link_id.trim();
    try {
      await onCreate(payload);
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create entry.");
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-entry-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-auto rounded-lg border border-zinc-200 bg-white p-4 shadow-lg dark:border-zinc-800 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="add-entry-title" className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Add journal entry
        </h2>
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          {error && (
            <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200">
              {error}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Trade date *</label>
              <input
                type="date"
                value={trade_date}
                onChange={(e) => setTradeDate(e.target.value)}
                required
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Symbol *</label>
              <input
                type="text"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="SPY"
                required
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Strategy</label>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              >
                <option value="SHARES">SHARES</option>
                <option value="CSP">CSP</option>
                <option value="CC">CC</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Action *</label>
              <select
                value={action}
                onChange={(e) => setAction(e.target.value)}
                required
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              >
                {ACTIONS.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Qty *</label>
              <input
                type="number"
                min={0}
                step={1}
                value={qty}
                onChange={(e) => setQty(Number(e.target.value) || 0)}
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Price (shares)</label>
              <input
                type="number"
                step={0.01}
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Premium (options)</label>
              <input
                type="number"
                step={0.01}
                value={premium}
                onChange={(e) => setPremium(e.target.value)}
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Fees</label>
              <input
                type="number"
                step={0.01}
                value={fees}
                onChange={(e) => setFees(e.target.value)}
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Realized P/L (on close)</label>
              <input
                type="number"
                step={0.01}
                value={realized_pl}
                onChange={(e) => setRealizedPl(e.target.value)}
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Contract key</label>
              <input
                type="text"
                value={contract_key}
                onChange={(e) => setContractKey(e.target.value)}
                placeholder="Option identifier"
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Expiry</label>
              <input
                type="date"
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Strike</label>
              <input
                type="number"
                step={0.01}
                value={strike}
                onChange={(e) => setStrike(e.target.value)}
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400">Right (P/C)</label>
              <input
                type="text"
                value={right}
                onChange={(e) => setRight(e.target.value)}
                placeholder="P or C"
                className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-zinc-500 dark:text-zinc-400">Link ID (group open/close)</label>
            <input
              type="text"
              value={link_id}
              onChange={(e) => setLinkId(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 dark:text-zinc-400">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 dark:text-zinc-400">Tags (comma-separated)</label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={isPending}>
              {isPending ? "Saving…" : "Add"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
