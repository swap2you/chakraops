/** S5: TRADE_BLOCKED_EARNINGS — execution_status BLOCKED, EARNINGS_WINDOW */
import type { ScenarioBundle } from "@/types/views";

const dailyOverview = {
  date: "2026-02-02",
  run_mode: "DRY_RUN",
  config_frozen: true,
  freeze_violation_changed_keys: [] as string[],
  regime: "NEUTRAL",
  regime_reason: "VIX in range",
  symbols_evaluated: 52,
  selected_signals: 1,
  trades_ready: 0,
  no_trade: false,
  why_summary: "Trade plan available but blocked by earnings window.",
  top_blockers: [{ code: "EARNINGS_WINDOW", count: 1 }],
  risk_posture: "CONSERVATIVE",
  links: { latest_decision_ts: "2026-02-02T14:00:00Z" },
};

const tradePlan = {
  decision_ts: "2026-02-02T14:00:00Z",
  symbol: "AAPL",
  strategy_type: "CSP",
  proposal: { symbol: "AAPL", strategy_type: "CSP", expiry: "2026-04-17", strikes: [180], contracts: 1, credit_estimate: 120, max_loss: 240 },
  execution_status: "BLOCKED",
  user_acknowledged: false,
  execution_notes: "",
  exit_plan: {},
  computed_targets: { t1: 72, t2: 54, t3: 27 },
  blockers: ["EARNINGS_WINDOW"],
};

const positions: ScenarioBundle["positions"] = [];
const decisionHistory: ScenarioBundle["decisionHistory"] = [
  { date: "2026-02-02", evaluated_at: "2026-02-02T14:00:00Z", outcome: "TRADE" as const, rationale: "Trade plan blocked by earnings window.", overview: dailyOverview, trade_plan: tradePlan, positions },
];

export const bundle: ScenarioBundle = { dailyOverview, tradePlan, positions, alerts: { as_of: "2026-02-02T14:00:00Z", items: [] }, decisionHistory };
