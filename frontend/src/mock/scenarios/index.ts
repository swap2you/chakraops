/**
 * Phase 8.5: Scenario registry — maps scenario keys to coherent data bundles.
 * Used in MOCK mode only. Selection persisted in localStorage.
 */
import type { ScenarioBundle } from "@/types/views";

import { bundle as s01 } from "./s01_trade_ready_clean";
import { bundle as s02 } from "./s02_no_trade_no_setups";
import { bundle as s03 } from "./s03_no_trade_low_liquidity";
import { bundle as s04 } from "./s04_risk_hold_regime_off";
import { bundle as s05 } from "./s05_trade_blocked_earnings";
import { bundle as s06 } from "./s06_trade_ready_many_evaluated";
import { bundle as s07 } from "./s07_trade_ready_missing_targets";
import { bundle as s08 } from "./s08_history_partial_overview";
import { bundle as s09 } from "./s09_pos_near_expiry";
import { bundle as s10 } from "./s10_pos_needs_attention_stop";
import { bundle as s11 } from "./s11_pos_partially_closed";
import { bundle as s12 } from "./s12_pos_assigned";
import { bundle as s13 } from "./s13_pos_closed_negative_pnl";
import { bundle as s14 } from "./s14_alerts_conflicting_hold";
import { bundle as s15 } from "./s15_alert_spam_day";
import { bundle as s16 } from "./s16_multi_eval_same_day";
import { bundle as s17 } from "./s17_date_filter_empty";
import { bundle as s18 } from "./s18_stress_250_50";

export const SCENARIO_KEYS = [
  "S1_TRADE_READY_CLEAN",
  "S2_NO_TRADE_NO_SETUPS",
  "S3_NO_TRADE_LOW_LIQUIDITY",
  "S4_RISK_HOLD_REGIME_OFF",
  "S5_TRADE_BLOCKED_EARNINGS",
  "S6_TRADE_READY_MANY_EVALUATED",
  "S7_TRADE_READY_MISSING_TARGETS",
  "S8_HISTORY_PARTIAL_OVERVIEW",
  "S9_POS_OPEN_NEAR_EXPIRY",
  "S10_POS_NEEDS_ATTENTION_STOP",
  "S11_POS_PARTIALLY_CLOSED",
  "S12_POS_ASSIGNED",
  "S13_POS_CLOSED_NEGATIVE_PNL",
  "S14_ALERTS_CONFLICTING_HOLD",
  "S15_ALERT_SPAM_DAY",
  "S16_MULTI_EVAL_SAME_DAY",
  "S17_DATE_FILTER_EMPTY",
  "S18_STRESS_250_50",
] as const;

export type ScenarioKey = (typeof SCENARIO_KEYS)[number];

const BUNDLES: Record<ScenarioKey, ScenarioBundle> = {
  S1_TRADE_READY_CLEAN: s01,
  S2_NO_TRADE_NO_SETUPS: s02,
  S3_NO_TRADE_LOW_LIQUIDITY: s03,
  S4_RISK_HOLD_REGIME_OFF: s04,
  S5_TRADE_BLOCKED_EARNINGS: s05,
  S6_TRADE_READY_MANY_EVALUATED: s06,
  S7_TRADE_READY_MISSING_TARGETS: s07,
  S8_HISTORY_PARTIAL_OVERVIEW: s08,
  S9_POS_OPEN_NEAR_EXPIRY: s09,
  S10_POS_NEEDS_ATTENTION_STOP: s10,
  S11_POS_PARTIALLY_CLOSED: s11,
  S12_POS_ASSIGNED: s12,
  S13_POS_CLOSED_NEGATIVE_PNL: s13,
  S14_ALERTS_CONFLICTING_HOLD: s14,
  S15_ALERT_SPAM_DAY: s15,
  S16_MULTI_EVAL_SAME_DAY: s16,
  S17_DATE_FILTER_EMPTY: s17,
  S18_STRESS_250_50: s18,
};

export const SCENARIO_LABELS: Record<ScenarioKey, string> = {
  S1_TRADE_READY_CLEAN: "S1 Trade ready (clean)",
  S2_NO_TRADE_NO_SETUPS: "S2 No trade (no setups)",
  S3_NO_TRADE_LOW_LIQUIDITY: "S3 No trade (low liquidity)",
  S4_RISK_HOLD_REGIME_OFF: "S4 Risk hold (regime off)",
  S5_TRADE_BLOCKED_EARNINGS: "S5 Trade blocked (earnings)",
  S6_TRADE_READY_MANY_EVALUATED: "S6 Trade ready (many evaluated)",
  S7_TRADE_READY_MISSING_TARGETS: "S7 Trade ready (missing targets)",
  S8_HISTORY_PARTIAL_OVERVIEW: "S8 History partial overview",
  S9_POS_OPEN_NEAR_EXPIRY: "S9 Position near expiry",
  S10_POS_NEEDS_ATTENTION_STOP: "S10 Position needs attention (stop)",
  S11_POS_PARTIALLY_CLOSED: "S11 Position partially closed",
  S12_POS_ASSIGNED: "S12 Position assigned",
  S13_POS_CLOSED_NEGATIVE_PNL: "S13 Position closed (negative PnL)",
  S14_ALERTS_CONFLICTING_HOLD: "S14 Alerts conflicting with hold",
  S15_ALERT_SPAM_DAY: "S15 Alert spam day",
  S16_MULTI_EVAL_SAME_DAY: "S16 Multi eval same day",
  S17_DATE_FILTER_EMPTY: "S17 Date filter empty",
  S18_STRESS_250_50: "S18 Stress (250 history, 50 positions)",
};

export function getScenarioBundle(key: ScenarioKey): ScenarioBundle {
  const b = BUNDLES[key];
  if (!b) throw new Error(`Unknown scenario: ${key}`);
  return b;
}

export function getDefaultScenarioKey(): ScenarioKey {
  return "S1_TRADE_READY_CLEAN";
}
