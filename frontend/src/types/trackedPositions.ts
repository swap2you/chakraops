/**
 * Phase 1: Tracked position types for manual execution.
 * Matches backend app.core.positions.models.
 */

export type PositionStatus = "OPEN" | "PARTIAL_EXIT" | "CLOSED" | "ABORTED";
export type PositionStrategy = "CSP" | "CC" | "STOCK";

export interface TrackedPosition {
  position_id: string;
  account_id: string;
  symbol: string;
  strategy: PositionStrategy;
  contracts: number;
  strike: number | null;
  expiration: string | null;
  credit_expected: number | null;
  quantity: number | null;
  status: PositionStatus;
  opened_at: string;
  closed_at: string | null;
  notes: string;
  /** Phase 2C: Lifecycle state from last directive */
  lifecycle_state?: string | null;
  /** Phase 2C: Last directive text (e.g. EXIT 1 CONTRACT) */
  last_directive?: string | null;
  /** Phase 2C: Timestamp of last lifecycle alert */
  last_alert_at?: string | null;
}

export interface TrackedPositionsListResponse {
  positions: TrackedPosition[];
  count: number;
  error?: string;
}

/** Payload for manual execution. */
export interface ManualExecutePayload {
  account_id: string;
  symbol: string;
  strategy: PositionStrategy;
  contracts?: number;
  strike?: number | null;
  expiration?: string | null;
  credit_expected?: number | null;
  quantity?: number | null;
  notes?: string;
}
