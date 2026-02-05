/**
 * Types for Trade Journal: trades, fills, and alerts.
 * Matches backend app.core.journal.models and API responses.
 */

export type FillAction = "OPEN" | "CLOSE";

export interface JournalFill {
  fill_id: string;
  trade_id: string;
  filled_at: string;
  action: FillAction;
  qty: number;
  price: number;
  fees: number;
  tags: string[];
}

/** Next action from exit-rules engine (EOD), set by nightly job */
export interface NextAction {
  action: string;
  severity: string;
  message: string;
  rule_code?: string;
  evaluated_at?: string;
}

export interface JournalTrade {
  trade_id: string;
  symbol: string;
  strategy: string;
  opened_at: string;
  expiry: string | null;
  strike: number | null;
  side: string;
  contracts: number;
  entry_mid_est: number | null;
  run_id: string | null;
  notes: string | null;
  stop_level: number | null;
  target_levels: number[];
  fills: JournalFill[];
  remaining_qty: number;
  avg_entry: number | null;
  avg_exit: number | null;
  realized_pnl: number | null;
  /** From exit-rules (CSP/CC); set after nightly run */
  next_action?: NextAction | null;
}

export interface TradesListResponse {
  trades: JournalTrade[];
  count: number;
  error?: string;
}

export interface TradeAlertResponse {
  trade_id: string;
  symbol: string;
  alert_type: string;
  message: string;
  level?: number;
  current_price?: number;
  meta?: Record<string, unknown>;
  created_at?: string;
}

export interface TradesAlertsResponse {
  alerts: TradeAlertResponse[];
  count: number;
  error?: string;
}

/** Payload for creating/updating a trade (partial for update). */
export interface TradePayload {
  trade_id?: string;
  symbol?: string;
  strategy?: string;
  opened_at?: string;
  expiry?: string | null;
  strike?: number | null;
  side?: string;
  contracts?: number;
  entry_mid_est?: number | null;
  run_id?: string | null;
  notes?: string | null;
  stop_level?: number | null;
  target_levels?: number[];
}

/** Payload for adding a fill. */
export interface FillPayload {
  fill_id?: string;
  filled_at: string;
  action: FillAction;
  qty: number;
  price: number;
  fees?: number;
  tags?: string[];
}
