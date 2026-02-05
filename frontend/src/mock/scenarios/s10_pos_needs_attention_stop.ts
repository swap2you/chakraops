/** S10: POS_OPEN_NEEDS_ATTENTION_STOP — needs_attention true, STOP_APPROACHING, next action "Consider stop", status amber */
import type { ScenarioBundle } from "@/types/views";

const dailyOverview = {
  date: "2026-02-07",
  run_mode: "DRY_RUN",
  config_frozen: true,
  freeze_violation_changed_keys: [] as string[],
  regime: "NEUTRAL",
  regime_reason: "VIX in range",
  symbols_evaluated: 52,
  selected_signals: 0,
  trades_ready: 0,
  no_trade: true,
  why_summary: "No READY setup.",
  top_blockers: [] as Array<{ code: string; count: number }>,
  risk_posture: "CONSERVATIVE",
  links: { latest_decision_ts: "2026-02-07T14:00:00Z" },
};

const positions: ScenarioBundle["positions"] = [
  { position_id: "pos-stop", symbol: "QQQ", strategy_type: "CSP", lifecycle_state: "OPEN", opened: "2026-01-20", expiry: "2026-03-20", strike: 380, contracts: 1, entry_credit: 180, last_mark: 30, dte: 25, unrealized_pnl: null, realized_pnl: 0, max_loss_estimate: 360, profit_targets: { t1: 72, t2: 54, t3: 27 }, notes: "", needs_attention: true, attention_reasons: ["STOP_APPROACHING"] },
];

const decisionHistory: ScenarioBundle["decisionHistory"] = [
  { date: "2026-02-07", evaluated_at: "2026-02-07T14:00:00Z", outcome: "NO_TRADE", rationale: "No READY setup.", overview: dailyOverview, trade_plan: null, positions },
];

export const bundle: ScenarioBundle = { dailyOverview, tradePlan: null, positions, alerts: { as_of: "2026-02-07T14:00:00Z", items: [] }, decisionHistory };
