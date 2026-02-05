/** S8: HISTORY_RECORD_PARTIAL_OVERVIEW — DecisionRecord with overview null; list row + detail placeholders */
import type { ScenarioBundle } from "@/types/views";

const dailyOverview = {
  date: "2026-02-05",
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
  links: { latest_decision_ts: "2026-02-05T14:00:00Z" },
};

const positions: ScenarioBundle["positions"] = [];

const decisionHistory: ScenarioBundle["decisionHistory"] = [
  { date: "2026-02-05", evaluated_at: "2026-02-05T14:00:00Z", outcome: "NO_TRADE" as const, rationale: "Data unavailable for this record.", overview: dailyOverview, trade_plan: null, positions },
  { date: "2026-02-04", evaluated_at: "2026-02-04T10:00:00Z", outcome: "NO_TRADE" as const, rationale: "Partial record — overview missing.", overview: undefined, trade_plan: null, positions },
];

export const bundle: ScenarioBundle = { dailyOverview, tradePlan: null, positions, alerts: { as_of: "2026-02-05T14:00:00Z", items: [] }, decisionHistory };
