# Phase 12.0 — Fill workflow + realized PnL correctness + portfolio metrics

## Premium field standardization

- **open_credit** / **credit_expected**: Total premium in dollars (all contracts). Not per-share.
- **close_debit**: Total debit paid at close = `close_price * 100 * contracts`.
- **realized_pnl** = `open_credit - close_debit - open_fees - close_fees`

## Contract identity (options)

- For CSP, CC (and spreads later): `contract_key` OR `option_symbol` is **required** on POST /api/ui/positions.
- If missing → 409.
- No server-side derivation of contract_key; use provider-backed values only.

## Portfolio metrics

- GET /api/ui/portfolio/metrics?account_id=...
- Returns: open_positions_count, capital_deployed, realized_pnl_total, win_rate, avg_pnl, avg_credit, avg_dte_at_entry.
