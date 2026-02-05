/** S4: RISK_HOLD_REGIME_OFF — outcome RISK_HOLD, regime RISK_OFF, hold styling/copy */
import type { ScenarioBundle } from "@/types/views";

const dailyOverview = {
  date: "2026-01-29",
  run_mode: "DRY_RUN",
  config_frozen: true,
  freeze_violation_changed_keys: [] as string[],
  regime: "RISK_OFF",
  regime_reason: "VIX elevated",
  symbols_evaluated: 52,
  selected_signals: 2,
  trades_ready: 0,
  no_trade: true,
  why_summary: "Regime or risk posture indicates holding. Review positions and constraints.",
  top_blockers: [{ code: "REGIME_RISK_OFF", count: 1 }],
  risk_posture: "DEFENSIVE",
  links: { latest_decision_ts: "2026-01-29T14:00:00Z" },
};

const positions: ScenarioBundle["positions"] = [
  { position_id: "pos-1", symbol: "SPY", strategy_type: "CSP", lifecycle_state: "OPEN", opened: "2026-01-15", expiry: "2026-03-21", strike: 450, contracts: 1, entry_credit: 250, last_mark: null, dte: 47, unrealized_pnl: null, realized_pnl: 0, max_loss_estimate: 500, profit_targets: { t1: 100, t2: 75, t3: 37.5 }, notes: "", needs_attention: false, attention_reasons: [] },
];

const decisionHistory: ScenarioBundle["decisionHistory"] = [
  { date: "2026-01-29", evaluated_at: "2026-01-29T14:00:00Z", outcome: "RISK_HOLD" as const, rationale: "Regime or risk posture indicates holding. Review positions and constraints.", overview: dailyOverview, trade_plan: null, positions },
];

export const bundle: ScenarioBundle = { dailyOverview, tradePlan: null, positions, alerts: { as_of: "2026-01-29T14:00:00Z", items: [] }, decisionHistory };
