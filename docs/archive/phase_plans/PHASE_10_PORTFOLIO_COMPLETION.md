# Phase 10 — Portfolio & Score Clarity

## Phase 10 — Portfolio & Score Clarity

## Phase 10.0 — Portfolio Completion

Close/delete positions, account config, correct capital (collateral).

## Backend

### Position Schema (Phase 10 fields)

- `id`, `account_id`, `status` (OPEN/CLOSED)
- `underlying`, `strategy` (CSP/CC), `option_type` (PUT/CALL), `strike`, `expiry`, `contracts`
- `open_credit`, `open_price`, `open_fees`, `open_time_utc`
- `close_debit`, `close_price`, `close_fees`, `close_time_utc`
- `collateral` (CSP/CC: strike×100×contracts), `realized_pnl`
- `is_test` (DIAG_TEST or user-created test; excluded from totals by default)
- `created_at_utc`, `updated_at_utc`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ui/positions/{id}/close` | Close OPEN position. Body: `close_price` (required), `close_time_utc?`, `close_fees?` |
| DELETE | `/api/ui/positions/{id}` | Delete position. Allowed only when `is_test=true` OR `status=CLOSED`/`ABORTED`. Returns 409 otherwise. |
| GET | `/api/ui/accounts` | List all accounts |
| POST | `/api/ui/accounts` | Create account. Body: provider, account_type, total_capital, max_capital_per_trade_pct, max_total_exposure_pct, allowed_strategies |

### Portfolio Totals

- `capital_deployed` = sum(collateral) for OPEN positions
- `open_positions_count` = count of OPEN/PARTIAL_EXIT
- `exclude_test=true` (default) excludes `is_test` positions from totals and default views
- GET `/api/ui/portfolio` and GET `/api/ui/positions/tracked` return `capital_deployed` and `open_positions_count`

## Frontend

- **Portfolio page**: Close button for OPEN positions → drawer with close price/time; Delete button for CLOSED or test positions
- **Account panel**: Select account; show buying_power, risk_per_trade, open_positions_count
- **Dashboard**: Use `collateral` (not notional) for capital deployed and position amounts

---

## Phase 10.1 — Score Clarity Overhaul

Plumbing and display only; no scoring algorithm changes.

### Backend

- Decision/universe and symbol-diagnostics responses include:
  - `raw_score` — composite before any cap
  - `pre_cap_score` — same as raw_score (alias)
  - `final_score` — after caps; **band is derived from this only**
  - `score_caps` — `{ regime_cap?, applied_caps: [{ type, cap_value, before, after, reason }] }`
- Band is computed only from final score: `assign_band(final_score or score)` in artifact `from_dict`; evaluation service uses `assign_band(score)` where score is the final (capped) value.
- Ranking service `_get_composite_score` uses `final_score` or `score` (post-cap) for ordering.

### Frontend

- **Universe row** tooltip: "Raw: X → Final: Y (reason)" when caps exist.
- **Symbol diagnostics header**: "Final score X (capped from Y)" when caps exist; uses `final_score` and `raw_score`.
- Types: `SymbolEvalSummary` and symbol diagnostics include `final_score`, `pre_cap_score`.
