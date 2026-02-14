/**
 * Phase 3: Portfolio & Risk Intelligence types.
 */

export interface PortfolioSummary {
  total_equity: number;
  capital_in_use: number;
  available_capital: number;
  capital_utilization_pct: number;
  open_positions_count: number;
  available_capital_clamped: boolean;
  risk_flags: RiskFlag[];
  error?: string;
}

export interface RiskFlag {
  code: string;
  message: string;
  severity: "error" | "warning";
}

export interface ExposureItem {
  key: string;
  required_capital: number;
  pct_of_total_equity: number;
  pct_of_available_capital: number;
  position_count: number;
}

export interface PortfolioExposureResponse {
  items: ExposureItem[];
  group_by: "symbol" | "sector";
  error?: string;
}

export interface RiskProfile {
  max_capital_utilization_pct: number;
  max_single_symbol_exposure_pct: number;
  max_single_sector_exposure_pct: number;
  max_open_positions: number;
  max_positions_per_sector: number;
  allowlist_symbols: string[];
  denylist_symbols: string[];
  preferred_strategies: string[];
  stop_loss_cooldown_days: number | null;
  error?: string;
}

/** Phase 8.4: Portfolio dashboard — snapshot + stress simulation. */
export interface PortfolioDashboardSnapshot {
  as_of?: string;
  total_open_positions?: number;
  open_csp_count?: number;
  open_cc_count?: number;
  total_capital_committed?: number;
  exposure_pct?: number | null;
  avg_premium_capture?: number | null;
  weighted_dte?: number | null;
  assignment_risk?: { status?: string; notional_itm_risk?: number | null; positions_near_itm?: number | null };
  symbol_concentration?: { top_symbols?: Array<{ symbol: string; committed: number; pct_of_committed: number }>; max_symbol_pct?: number | null };
  sector_breakdown?: { status?: string; by_sector?: Array<{ sector: string; committed: number; pct_of_committed: number }> };
  cluster_risk_level?: string;
  regime_adjusted_exposure?: number | null;
  warnings?: string[];
}

export interface PortfolioDashboardStressScenario {
  shock_pct: number;
  estimated_assignments: number;
  assignment_capital_required: number;
  estimated_unrealized_drawdown: number;
  starting_equity?: number | null;
  shocked_equity?: number | null;
  equity_drawdown_pct?: number | null;
  csp_reserved_cash?: number;
  cc_equity_notional?: number;
  total_notional_post_shock?: number;
  post_shock_exposure_pct?: number | null;
  cash_buffer?: number | null;
  survival_status?: string;
  notes?: string[];
}

export interface PortfolioDashboardStress {
  scenarios: PortfolioDashboardStressScenario[];
  worst_case?: {
    shock_pct?: number | null;
    estimated_unrealized_drawdown?: number;
    shocked_equity?: number | null;
    post_shock_exposure_pct?: number | null;
    cash_buffer?: number | null;
    survival_status?: string;
  };
  warnings?: string[];
}

export interface PortfolioDashboardResponse {
  snapshot: PortfolioDashboardSnapshot;
  stress: PortfolioDashboardStress;
  error?: string;
}
