/** S17: DATE_FILTER_EMPTY — one decision; filtering to other dates yields 0 records, UI shows calm empty state */
import type { ScenarioBundle } from "@/types/views";

const dailyOverview = { date: "2026-02-14", run_mode: "DRY_RUN", config_frozen: true, freeze_violation_changed_keys: [], regime: "NEUTRAL", regime_reason: "VIX in range", symbols_evaluated: 52, selected_signals: 0, trades_ready: 0, no_trade: true, why_summary: "No READY setup.", top_blockers: [], risk_posture: "CONSERVATIVE", links: { latest_decision_ts: "2026-02-14T14:00:00Z" } };

const positions: ScenarioBundle["positions"] = [];
const decisionHistory: ScenarioBundle["decisionHistory"] = [
  { date: "2026-02-14", evaluated_at: "2026-02-14T14:00:00Z", outcome: "NO_TRADE", rationale: "No READY setup.", overview: dailyOverview, trade_plan: null, positions },
];

export const bundle: ScenarioBundle = { dailyOverview, tradePlan: null, positions, alerts: { as_of: "2026-02-14T14:00:00Z", items: [] }, decisionHistory };
