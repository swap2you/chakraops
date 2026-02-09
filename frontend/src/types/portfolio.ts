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
