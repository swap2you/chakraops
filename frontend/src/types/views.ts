/**
 * Read-model types matching Phase 6.5 UI contracts.
 * UI consumes these only; no business logic.
 */

export interface PositionView {
  position_id: string | number
  symbol: string
  strategy_type: string
  lifecycle_state: string
  opened: string
  expiry: string | null
  strike: number | [number, number] | null
  contracts: number
  entry_credit: number | null
  last_mark: number | null
  dte: number | null
  unrealized_pnl: number | null
  realized_pnl: number
  max_loss_estimate: number | null
  profit_targets: Record<string, number>
  notes: string
  needs_attention: boolean
  attention_reasons: string[]
}

export interface DailyOverviewView {
  date: string
  run_mode: string
  config_frozen: boolean
  freeze_violation_changed_keys: string[]
  regime: string | null
  regime_reason: string | null
  symbols_evaluated: number
  selected_signals: number
  trades_ready: number
  no_trade: boolean
  why_summary: string
  top_blockers: Array<{ code: string; count: number }>
  risk_posture: string
  links: Record<string, string>
  /** LIVE: ISO timestamp when this overview was fetched from API */
  fetched_at?: string | null
}

export interface TradePlanView {
  decision_ts: string
  symbol: string
  strategy_type: string
  proposal: Record<string, unknown>
  execution_status: string
  user_acknowledged: boolean
  execution_notes: string
  exit_plan: Record<string, unknown>
  /** Optional for S7 (missing targets); UI shows "—" when absent */
  computed_targets?: Record<string, number>
  blockers: string[]
}

export interface AlertsView {
  as_of: string
  items: Array<{
    level?: string
    code?: string
    message?: string
    symbol?: string
    position_id?: string
    decision_ts?: string
  }>
}

/** Phase 8: Immutable decision audit record. Read-only list + detail context. */
export type DecisionOutcome = "TRADE" | "NO_TRADE" | "RISK_HOLD";

export interface DecisionRecord {
  date: string
  evaluated_at: string
  outcome: DecisionOutcome
  rationale: string
  /** Optional for S8 (partial overview); detail drawer shows placeholders when absent */
  overview?: DailyOverviewView | null
  trade_plan: TradePlanView | null
  positions: PositionView[]
}

/** Phase 8.5: Coherent scenario bundle for MOCK mode. */
export interface ScenarioBundle {
  dailyOverview: DailyOverviewView | null
  tradePlan: TradePlanView | null
  positions: PositionView[]
  alerts: AlertsView | null
  decisionHistory: DecisionRecord[]
}
