# Accounts & Capital Awareness — Phase 1

## Why Accounts Exist

ChakraOps is a **decision + capital-aware trade management system**. It helps you decide *what* to trade and *how many contracts* to allocate — but it **never places trades**.

Accounts exist so that:

1. **Position sizing is realistic** — CSP recommendations show contract counts based on your actual capital, not arbitrary defaults.
2. **Capital limits are explicit** — max per-trade and total exposure percentages prevent over-allocation.
3. **Multi-account support** — you can track Roth, IRA, taxable, etc. separately.
4. **Future lifecycle management** — accounts are the foundation for CC overlays, exit alerts, and portfolio-level risk (Phase 2+).

## Manual Execution Philosophy

ChakraOps operates under a strict **manual execution** model:

- **No broker APIs** — ChakraOps does not integrate with Robinhood, Schwab, Fidelity, or any brokerage.
- **No auto-execution** — The "Execute" button does NOT place a trade. It records your *intention* to trade.
- **User responsibility** — After clicking Execute, *you* must open your brokerage and place the trade.
- **Trust but verify** — ChakraOps tracks what you *said* you would execute, enabling lifecycle management.

This design is intentional:

- **Safety** — No risk of accidental live trades.
- **Explicitness** — Every position is a conscious decision by the user.
- **Flexibility** — Works with any brokerage, even ones without APIs.
- **Auditability** — Every tracked position has a clear creation timestamp and account association.

## How CSP Sizing Works

When you look at a candidate CSP trade on the Ticker page, ChakraOps computes position sizing:

```
max_capital = account.total_capital * (account.max_capital_per_trade_pct / 100)
csp_notional = strike * 100
recommended_contracts = floor(max_capital / csp_notional)
```

### Example

| Field | Value |
|-------|-------|
| Total capital | $50,000 |
| Max per trade | 10% |
| Max capital | $5,000 |
| Strike price | $25.00 |
| CSP notional (per contract) | $2,500 |
| **Recommended contracts** | **2** |
| Capital required | $5,000 |

### When recommended_contracts == 0

If the account cannot afford even one contract at the given strike:

- The recommendation is **suppressed** (no CSP recommended)
- The verdict is overridden to **HOLD**
- The reason explains: "Insufficient capital for CSP at this strike"

This prevents the system from suggesting trades that the user cannot realistically execute.

## Data Model

### Account

| Field | Type | Description |
|-------|------|-------------|
| `account_id` | string | Unique, user-defined identifier |
| `provider` | string | Robinhood, Schwab, Fidelity, or Manual |
| `account_type` | string | Taxable, Roth, IRA, or 401k |
| `total_capital` | float | Total capital in USD (must be > 0) |
| `max_capital_per_trade_pct` | float | Max % of capital per trade (1-100) |
| `max_total_exposure_pct` | float | Max % of total exposure (1-100) |
| `allowed_strategies` | list | Subset of [CSP, CC, STOCK] |
| `is_default` | bool | Only one default account allowed |
| `active` | bool | Whether account is active |

### Position (Tracked)

| Field | Type | Description |
|-------|------|-------------|
| `position_id` | string | Auto-generated unique ID |
| `account_id` | string | Which account this belongs to |
| `symbol` | string | Ticker symbol |
| `strategy` | string | CSP, CC, or STOCK |
| `contracts` | int | Number of option contracts |
| `strike` | float | Strike price (null for STOCK) |
| `expiration` | string | Expiration date (null for STOCK) |
| `credit_expected` | float | Expected credit per contract |
| `quantity` | int | Number of shares (STOCK only) |
| `status` | string | OPEN, PARTIAL_EXIT, or CLOSED |
| `notes` | string | User notes |

## Persistence

- Accounts: `out/accounts/accounts.json`
- Positions: `out/positions/positions.json`

Both persist as JSON files and survive server restarts.

## API Endpoints

### Accounts

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/accounts` | List all accounts |
| POST | `/api/accounts` | Create account |
| PUT | `/api/accounts/{id}` | Update account |
| POST | `/api/accounts/{id}/set-default` | Set as default |
| GET | `/api/accounts/default` | Get default account |
| GET | `/api/accounts/{id}/csp-sizing?strike=X` | Compute CSP sizing |

### Positions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/positions/tracked` | List tracked positions |
| POST | `/api/positions/manual-execute` | Record manual execution |

## Integration with Scoring

The scoring engine (`app/core/eval/scoring.py`) uses the default account's `total_capital` for the `account_equity` used in capital efficiency scoring. Priority:

1. `ACCOUNT_EQUITY` environment variable (override for testing/CI)
2. Default account's `total_capital` (Phase 1 accounts system)
3. `config/scoring.yaml` `account_equity` (legacy fallback)

## What ChakraOps Never Does

- **Never** integrates with brokerage APIs
- **Never** places, modifies, or cancels real trades
- **Never** auto-executes based on signals
- **Never** accesses brokerage account data programmatically

All execution is manual. All positions are user-recorded. This is by design.
