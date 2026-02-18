/**
 * Reason code → human description. UI owns mapping; backend returns codes only.
 * Used when reasons_explained is empty and we parse primary_reason.
 * rejected_due_to_delta=N is a count, NOT a delta value — display as rejected_count=N.
 */

export interface ReasonDefinition {
  title: string;
  /** Message template. {value} = parsed numeric (e.g. rejected_count); {lo}, {hi} = target range. */
  template: (opts: { value?: number; lo?: number; hi?: number }) => string;
  severity: "blocker" | "FAIL" | "WARN" | "INFO";
  docsLink?: string;
}

export const REASON_DEFINITIONS: Record<string, ReasonDefinition> = {
  rejected_due_to_delta: {
    title: "Delta outside target range",
    template: ({ value }) =>
      value != null
        ? `Rejected due to delta band (rejected_count=${value}).`
        : "No put contracts in delta band (abs(delta) 0.20–0.40). See diagnostics for details.",
    severity: "FAIL",
  },
  DATA_INCOMPLETE: {
    title: "Data incomplete",
    template: () => "Required data missing. See diagnostics for details.",
    severity: "FAIL",
  },
  FAIL_RSI_RANGE: {
    title: "RSI outside preferred range",
    template: () => "RSI outside preferred range.",
    severity: "FAIL",
  },
  FAIL_NOT_NEAR_SUPPORT: {
    title: "Not near support",
    template: () => "Not near support.",
    severity: "FAIL",
  },
  FAIL_NO_HOLDINGS: {
    title: "No shares held",
    template: () => "No shares held; covered calls disabled.",
    severity: "FAIL",
  },
  CONTRACT_SELECTION_FAIL: {
    title: "No contract passed filters",
    template: () => "No contracts passed option liquidity and delta filters.",
    severity: "FAIL",
  },
  FAIL_RSL_CC: {
    title: "RSL / CC",
    template: () => "Rejected (RSL / CC).",
    severity: "FAIL",
  },
  OTHER: {
    title: "Reason",
    template: ({ value }) => (value != null ? String(value) : "See diagnostics for details."),
    severity: "WARN",
  },
};
