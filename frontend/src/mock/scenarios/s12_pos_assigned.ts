import type { ScenarioBundle } from "@/types/views";

const dailyOverview = {
  date: "2026-02-09", run_mode: "DRY_RUN", config_frozen: true, freeze_violation_changed_keys: [] as string[],
  regime: "NEUTRAL", regime_reason: "VIX in range", symbols_evaluated: 52, selected_signals: 0, trades_ready: 0, no_trade: true,
  why_summary: "No READY setup.", top_blockers: [] as Array<{ code: string; count: number }>, risk_posture: "CONSERVATIVE",
  links: { latest_decision_ts: "2026-02-09T14:00:00Z" },
};

const positions: ScenarioBundle["positions"] = [
  { position_id: "pos-assigned", symbol: "SPY", strategy_type: "CSP", lifecycle_state: "ASSIGNED", opened: "2026-01-05", expiry: "2026-02-07", strike: 450, contracts: 1, entry_credit: 250, last_mark: null, dte: null, unrealized_pnl: null, realized_pnl: -20, max_loss_estimate: 500, profit_targets: {}, notes: "", needs_attention: false, attention_reasons: [] },
];

const decisionHistory: ScenarioBundle["decisionHistory"] = [
  { date: "2026-02-09", evaluated_at: "2026-02-09T14:00:00Z", outcome: "NO_TRADE", rationale: "No READY setup.", overview: dailyOverview, trade_plan: null, positions },
];

export const bundle: ScenarioBundle = { dailyOverview, tradePlan: null, positions, alerts: { as_of: "2026-02-09T14:00:00Z", items: [] }, decisionHistory };
