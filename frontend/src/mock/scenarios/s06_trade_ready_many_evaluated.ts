/** S6: TRADE_READY_MANY_EVALUATED — symbols_evaluated 250, trades_ready 1 */
import type { ScenarioBundle } from "@/types/views";

const dailyOverview = {
  date: "2026-02-03",
  run_mode: "DRY_RUN",
  config_frozen: true,
  freeze_violation_changed_keys: [] as string[],
  regime: "NEUTRAL",
  regime_reason: "VIX in range",
  symbols_evaluated: 250,
  selected_signals: 1,
  trades_ready: 1,
  no_trade: false,
  why_summary: "1 safe trade available (SPY CSP).",
  top_blockers: [] as Array<{ code: string; count: number }>,
  risk_posture: "CONSERVATIVE",
  links: { latest_decision_ts: "2026-02-03T14:00:00Z" },
};

const tradePlan = {
  decision_ts: "2026-02-03T14:00:00Z",
  symbol: "SPY",
  strategy_type: "CSP",
  proposal: { symbol: "SPY", strategy_type: "CSP", expiry: "2026-04-18", strikes: [450], contracts: 1, credit_estimate: 260, max_loss: 520 },
  execution_status: "READY",
  user_acknowledged: false,
  execution_notes: "",
  exit_plan: {},
  computed_targets: { t1: 104, t2: 78, t3: 39 },
  blockers: [] as string[],
};

const positions: ScenarioBundle["positions"] = [];
const decisionHistory: ScenarioBundle["decisionHistory"] = [
  { date: "2026-02-03", evaluated_at: "2026-02-03T14:00:00Z", outcome: "TRADE" as const, rationale: "1 safe trade available (SPY CSP).", overview: dailyOverview, trade_plan: tradePlan, positions },
];

export const bundle: ScenarioBundle = { dailyOverview, tradePlan, positions, alerts: { as_of: "2026-02-03T14:00:00Z", items: [] }, decisionHistory };
