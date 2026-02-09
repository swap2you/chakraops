/**
 * Phase 4: Exit panel — manual exit entry for closed positions.
 * Required: exit_reason, exit_initiator, confidence_at_exit.
 */
import { useState, useEffect, useCallback } from "react";
import { apiGet, apiPost, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { pushSystemNotification } from "@/lib/notifications";
import type { ExitRecord, ExitReason, ExitInitiator } from "@/types/decisionQuality";
import type { PositionDetailWithExit } from "@/types/decisionQuality";
import { Loader2 } from "lucide-react";

const EXIT_REASONS: ExitReason[] = [
  "TARGET1",
  "TARGET2",
  "STOP_LOSS",
  "ABORT_REGIME",
  "ABORT_DATA",
  "MANUAL_EARLY",
  "EXPIRY",
  "ROLL",
];

const EXIT_INITIATORS: ExitInitiator[] = ["MANUAL", "LIFECYCLE_ENGINE"];

const EXIT_EVENT_TYPES = [
  { value: "FINAL_EXIT", label: "Final Exit (close position)" },
  { value: "SCALE_OUT", label: "Scale Out (partial exit)" },
] as const;

interface ExitPanelProps {
  positionId: string;
  symbol: string;
  status: string;
  onSuccess?: () => void;
}

export function ExitPanel({ positionId, symbol, status, onSuccess }: ExitPanelProps) {
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [exit, setExit] = useState<ExitRecord | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [form, setForm] = useState({
    exit_date: new Date().toISOString().slice(0, 10),
    exit_price: "",
    realized_pnl: "",
    fees: "0",
    exit_reason: "EXPIRY" as ExitReason,
    exit_initiator: "MANUAL" as ExitInitiator,
    event_type: "FINAL_EXIT" as "SCALE_OUT" | "FINAL_EXIT",
    confidence_at_exit: 3,
    notes: "",
  });

  const canLogExit = status === "OPEN" || status === "PARTIAL_EXIT";

  const loadDetail = useCallback(async () => {
    if (loaded && exit) return;
    setLoading(true);
    try {
      const data = await apiGet<PositionDetailWithExit>(ENDPOINTS.positionDetail(positionId));
      if (data.exit) {
        setExit(data.exit);
        setForm({
          exit_date: data.exit.exit_date,
          exit_price: String(data.exit.exit_price),
          realized_pnl: String(data.exit.realized_pnl),
          fees: String(data.exit.fees),
          exit_reason: data.exit.exit_reason,
          exit_initiator: data.exit.exit_initiator,
          event_type: (data.exit as { event_type?: "SCALE_OUT" | "FINAL_EXIT" }).event_type ?? "FINAL_EXIT",
          confidence_at_exit: data.exit.confidence_at_exit,
          notes: data.exit.notes ?? "",
        });
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      pushSystemNotification({ source: "system", severity: "error", title: "Load failed", message: msg });
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [positionId, loaded, exit]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await apiPost(ENDPOINTS.positionLogExit(positionId), {
        exit_date: form.exit_date,
        exit_price: parseFloat(form.exit_price) || 0,
        realized_pnl: parseFloat(form.realized_pnl) || 0,
        fees: parseFloat(form.fees) || 0,
        exit_reason: form.exit_reason,
        exit_initiator: form.exit_initiator,
        event_type: form.event_type,
        confidence_at_exit: form.confidence_at_exit,
        notes: form.notes.slice(0, 1000),
      });
      pushSystemNotification({
        source: "system",
        severity: "info",
        title: "Exit logged",
        message: `${symbol} — position closed and exit recorded.`,
      });
      setLoaded(false);
      onSuccess?.();
    } catch (e: unknown) {
      const err = e instanceof ApiError ? e : undefined;
      const body = err?.body as { errors?: string[] } | undefined;
      const msgs = body?.errors ?? [err?.message ?? String(e)];
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "Exit log failed",
        message: msgs.join("; "),
      });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading && !loaded) {
    return (
      <div className="flex items-center justify-center gap-2 p-6 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading...
      </div>
    );
  }

  if (exit) {
    return (
      <div className="space-y-3 p-4 rounded-lg border border-border bg-muted/20">
        <h4 className="text-sm font-medium text-muted-foreground">Exit Recorded</h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <span className="text-muted-foreground">Date:</span>
          <span>{exit.exit_date}</span>
          <span className="text-muted-foreground">Reason:</span>
          <span>{exit.exit_reason}</span>
          <span className="text-muted-foreground">P&amp;L:</span>
          <span className={exit.realized_pnl >= 0 ? "text-emerald-600" : "text-red-600"}>
            ${exit.realized_pnl.toFixed(2)}
          </span>
        </div>
      </div>
    );
  }

  if (!canLogExit) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        Position is {status}. No exit entry for already-closed positions.
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-4 rounded-lg border border-border">
      <h4 className="text-sm font-medium">Log Exit</h4>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Exit Date (required)</label>
          <input
            type="date"
            required
            value={form.exit_date}
            onChange={(e) => setForm((f) => ({ ...f, exit_date: e.target.value }))}
            className="w-full rounded border border-input bg-background px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Exit Price</label>
          <input
            type="number"
            step="0.01"
            value={form.exit_price}
            onChange={(e) => setForm((f) => ({ ...f, exit_price: e.target.value }))}
            className="w-full rounded border border-input bg-background px-2 py-1.5 text-sm"
            placeholder="0"
          />
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Realized P&amp;L</label>
          <input
            type="number"
            step="0.01"
            value={form.realized_pnl}
            onChange={(e) => setForm((f) => ({ ...f, realized_pnl: e.target.value }))}
            className="w-full rounded border border-input bg-background px-2 py-1.5 text-sm"
            placeholder="0"
          />
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Fees</label>
          <input
            type="number"
            step="0.01"
            value={form.fees}
            onChange={(e) => setForm((f) => ({ ...f, fees: e.target.value }))}
            className="w-full rounded border border-input bg-background px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Event Type (required)</label>
          <select
            required
            value={form.event_type}
            onChange={(e) => setForm((f) => ({ ...f, event_type: e.target.value as "SCALE_OUT" | "FINAL_EXIT" }))}
            className="w-full rounded border border-input bg-background px-2 py-1.5 text-sm"
          >
            {EXIT_EVENT_TYPES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Exit Reason (required)</label>
          <select
            required
            value={form.exit_reason}
            onChange={(e) => setForm((f) => ({ ...f, exit_reason: e.target.value as ExitReason }))}
            className="w-full rounded border border-input bg-background px-2 py-1.5 text-sm"
          >
            {EXIT_REASONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Initiator (required)</label>
          <select
            required
            value={form.exit_initiator}
            onChange={(e) => setForm((f) => ({ ...f, exit_initiator: e.target.value as ExitInitiator }))}
            className="w-full rounded border border-input bg-background px-2 py-1.5 text-sm"
          >
            {EXIT_INITIATORS.map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Confidence 1–5 (required)</label>
          <select
            required
            value={form.confidence_at_exit}
            onChange={(e) => setForm((f) => ({ ...f, confidence_at_exit: parseInt(e.target.value, 10) }))}
            className="w-full rounded border border-input bg-background px-2 py-1.5 text-sm"
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label className="block text-xs text-muted-foreground mb-1">Notes</label>
        <textarea
          value={form.notes}
          onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value.slice(0, 1000) }))}
          rows={2}
          className="w-full rounded border border-input bg-background px-2 py-1.5 text-sm"
          placeholder="Optional"
        />
      </div>
      <button
        type="submit"
        disabled={submitting}
        className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        Log Exit and Close Position
      </button>
    </form>
  );
}
