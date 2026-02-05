/** S2: NO_TRADE_NO_SETUPS — outcome NO_TRADE, top_blockers NO_VALID_SETUP, trade_plan null, alerts empty */
import type { ScenarioBundle, AlertsView } from "@/types/views";

const dailyOverview = {
  date: "2026-01-31",
  run_mode: "DRY_RUN",
  config_frozen: true,
  freeze_violation_changed_keys: [] as string[],
  regime: "NEUTRAL",
  regime_reason: "VIX in range",
  symbols_evaluated: 48,
  selected_signals: 0,
  trades_ready: 0,
  no_trade: true,
  why_summary: "No READY setup met criteria. Capital remains protected.",
  top_blockers: [{ code: "NO_VALID_SETUP", count: 1 }],
  risk_posture: "CONSERVATIVE",
  links: { latest_decision_ts: "2026-01-31T13:30:00Z" },
};

const positions = [
  { position_id: "pos-1", symbol: "SPY", strategy_type: "CSP", lifecycle_state: "OPEN", opened: "2026-01-15", expiry: "2026-03-21", strike: 450, contracts: 1, entry_credit: 250, last_mark: null as number | null, dte: 46, unrealized_pnl: null as number | null, realized_pnl: 0, max_loss_estimate: 500, profit_targets: { t1: 100, t2: 75, t3: 37.5 }, notes: "", needs_attention: false, attention_reasons: [] as string[] },
];

const alerts = { as_of: "2026-01-31T13:30:00Z", items: [] as AlertsView["items"] };

const decisionHistory: ScenarioBundle["decisionHistory"] = [
  { date: "2026-01-31", evaluated_at: "2026-01-31T13:30:00Z", outcome: "NO_TRADE" as const, rationale: "No READY setup met criteria. Capital remains protected.", overview: dailyOverview, trade_plan: null, positions },
];

export const bundle: ScenarioBundle = { dailyOverview, tradePlan: null, positions, alerts, decisionHistory };
