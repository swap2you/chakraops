/**
 * Phase 1: Account types for capital awareness.
 * Matches backend app.core.accounts.models.
 */

export type Provider = "Robinhood" | "Schwab" | "Fidelity" | "Manual";
export type AccountType = "Taxable" | "Roth" | "IRA" | "401k";
export type Strategy = "CSP" | "CC" | "STOCK";

export interface Account {
  account_id: string;
  provider: Provider;
  account_type: AccountType;
  total_capital: number;
  max_capital_per_trade_pct: number;
  max_total_exposure_pct: number;
  allowed_strategies: Strategy[];
  is_default: boolean;
  created_at: string;
  updated_at: string;
  active: boolean;
}

export interface AccountsListResponse {
  accounts: Account[];
  count: number;
  error?: string;
}

export interface AccountDefaultResponse {
  account: Account | null;
  message?: string;
}

/** Payload for creating/updating an account. */
export interface AccountPayload {
  account_id?: string;
  provider: Provider;
  account_type: AccountType;
  total_capital: number;
  max_capital_per_trade_pct: number;
  max_total_exposure_pct: number;
  allowed_strategies: Strategy[];
  is_default?: boolean;
  active?: boolean;
}

/** CSP sizing response from backend. */
export interface CspSizingResponse {
  account_id: string;
  total_capital: number;
  max_capital_per_trade_pct: number;
  max_capital: number;
  strike: number;
  csp_notional: number;
  recommended_contracts: number;
  capital_required: number;
  eligible: boolean;
  verdict_override?: string;
  reason: string;
}

export const PROVIDERS: Provider[] = ["Robinhood", "Schwab", "Fidelity", "Manual"];
export const ACCOUNT_TYPES: AccountType[] = ["Taxable", "Roth", "IRA", "401k"];
export const STRATEGIES: Strategy[] = ["CSP", "CC", "STOCK"];
