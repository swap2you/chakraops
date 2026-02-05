import type { ScenarioBundle } from "@/types/views";

const dailyOverview = {
  date: "2026-01-30",
  run_mode: "DRY_RUN",
  config_frozen: true,
  freeze_violation_changed_keys: [] as string[],
  regime: "NEUTRAL",
  regime_reason: "VIX in range",
  symbols_evaluated: 50,
  selected_signals: 0,
  trades_ready: 0,
  no_trade: true,
  why_summary: "No READY setup met criteria.",
  top_blockers: [{ code: "LOW_LIQUIDITY", count: 1 }, { code: "WIDE_SPREAD", count: 1 }],
  risk_posture: "CONSERVATIVE",
  links: { latest_decision_ts: "2026-01-30T14:00:00Z" },
};

const positions: ScenarioBundle["positions"] = [];
const decisionHistory: ScenarioBundle["decisionHistory"] = [
  { date: "2026-01-30", evaluated_at: "2026-01-30T14:00:00Z", outcome: "NO_TRADE", rationale: "Liquidity and spread constraints.", overview: dailyOverview, trade_plan: null, positions },
];

export const bundle: ScenarioBundle = { dailyOverview, tradePlan: null, positions, alerts: { as_of: "2026-01-30T14:00:00Z", items: [] }, decisionHistory };
