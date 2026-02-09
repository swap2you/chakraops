/**
 * Phase 4: Decision quality types — outcome summary, strategy health, exit discipline.
 */

export type ExitReason =
  | "TARGET1"
  | "TARGET2"
  | "STOP_LOSS"
  | "ABORT_REGIME"
  | "ABORT_DATA"
  | "MANUAL_EARLY"
  | "EXPIRY"
  | "ROLL";

export type ExitInitiator = "LIFECYCLE_ENGINE" | "MANUAL";

export interface ExitRecord {
  position_id: string;
  exit_date: string;
  exit_price: number;
  realized_pnl: number;
  fees: number;
  exit_reason: ExitReason;
  exit_initiator: ExitInitiator;
  confidence_at_exit: number;
  notes: string;
}

export interface OutcomeSummary {
  status: "OK" | "INSUFFICIENT DATA" | "ERROR";
  win_count?: number;
  scratch_count?: number;
  loss_count?: number;
  unknown_risk_definition_count?: number;
  avg_time_in_trade_days?: number | null;
  avg_capital_days_used?: number | null;
  total_closed?: number;
  error?: string;
}

export interface StrategyHealth {
  status: "OK" | "INSUFFICIENT DATA" | "ERROR";
  strategies?: Record<
    string,
    {
      win_pct: number;
      loss_pct: number;
      abort_pct: number;
      avg_duration_days: number | null;
      count: number;
    }
  >;
  total_closed?: number;
  error?: string;
}

export interface PositionDetailWithExit {
  position_id: string;
  account_id: string;
  symbol: string;
  strategy: string;
  contracts: number;
  strike: number | null;
  expiration: string | null;
  credit_expected: number | null;
  quantity: number | null;
  status: string;
  opened_at: string;
  closed_at: string | null;
  notes: string;
  lifecycle_state?: string | null;
  last_directive?: string | null;
  last_alert_at?: string | null;
  exit?: ExitRecord | null;
}
