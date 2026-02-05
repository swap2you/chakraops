# ChakraOps Strategy Validation Report

**Generated:** 2026-01-30  
**Data Source:** ORATS Live Data (api.orats.io/datav2)  
**Endpoint:** `quote_bulk`

---

## 0. Pipeline Gates (Full Flow)

The decision pipeline applies the following gates in order. A symbol or candidate must pass each applicable gate to reach execution.

### 0.1 Market Regime Gate

- **Purpose:** Only allow new CSP/CC candidates when the market is in a risk-on regime.
- **Logic:** Risk-On when SPY > EMA200 and EMA50 > EMA200 (bullish trend). Risk-Off otherwise.
- **Implementation:** The main application (heartbeat/main) computes regime from SPY daily/weekly data and stores it; the pipeline can block candidates when regime is not RISK_ON. Realtime regime is available as a shadow in the dashboard.
- **Note:** The `run_and_save.py` pipeline does not currently fetch SPY/EMA; regime is used in the full heartbeat flow. For pipeline-only runs, regime is not enforced in `run_and_save.py`.

### 0.2 Symbol Eligibility Gate

- **Purpose:** Restrict universe to liquid, tradable names and avoid penny stocks.
- **Logic:**
  - **Liquidity:** Min average volume (e.g. 1.5M); min stock price (e.g. ≥ $10) from `guardrails.min_stock_price`.
  - **Earnings / news:** Not auto-filtered; manual pre-trade checklist (see Pre-Trade Checklist).
  - **Tradability:** Symbol must have listed options; snapshot provider must return a valid price.
- **Implementation:** `StockUniverseManager` applies min/max price and min avg volume; symbols from DB are the curated list. Min stock price is enforced from config.

### 0.3 Technical Setup Filter (Trend + Pullback + Reversal)

- **Purpose:** Prefer names in an uptrend with a pullback (for CSP) or trend alignment (for CC).
- **Logic:** Trend (e.g. price > EMA200), pullback (e.g. short-term dip), reversal (e.g. bounce). Exact rules are configurable in the full heartbeat/regime flow.
- **Implementation:** The signal engine in `run_and_save.py` does not apply trend/pullback/reversal filters; those are used in the main app’s candidate evaluation. Pipeline selection is based on DTE, OTM%, bid, and spread.

### 0.4 Scoring and Ranking

- **Weights:** Credit 50%, DTE 25%, liquidity 25% (no Delta/IV on Standard subscription).
- **Logic:** Each candidate gets component scores (premium, DTE, spread, OTM, liquidity) normalized to [0,1], then weighted sum. Rank by total score descending; select top N up to `max_total` and `max_per_symbol`.
- **Implementation:** `ScoringConfig(premium_weight=0.50, dte_weight=0.25, liquidity_weight=0.25, spread_weight=0, otm_weight=0)` in `run_and_save.py`.

### 0.5 Options Checks

- **Max spread width:** Bid-ask spread ≤ 25% (`max_spread_pct`).
- **Min credit:** Effective min credit ~$0.10; min bid ≥ $0.01.
- **Min bid:** $0.01 (configurable).
- **DTE:** 7–45 days (configurable).
- **OTM%:** CSP 3–20%, CC 2–15%.
- **Implementation:** Enforced in CSP/CC generators and chain normalization; rejections appear in exclusion summary.

### 0.6 Risk & Exit Logic

- **Max risk per trade:** Advisory; position sizing (e.g. ≤ 5% per name) is manual.
- **Profit target:** Close at X% of max profit (e.g. 50%) — `guardrails.take_profit_percent`; advisory; use `send_exit_alert(..., reason="EXIT", ...)` when hit.
- **Stop-loss / max loss:** Exit if underlying drops X% below CSP strike — `guardrails.stop_loss_percent` (e.g. 20%); advisory; use `send_exit_alert(..., reason="STOP", ...)` when hit.
- **Time-based exit:** Close or roll 7–14 days before expiration; manual or broker alerts.
- **Implementation:** Exit rules are advisory. When a position hits stop or target, call `app.notifications.slack_notifier.send_exit_alert(symbol, strike, reason="STOP"|"EXIT", detail=...)` to send a Slack notification.

### Standard Subscription Limitations and Compensation

- **Missing:** Delta, open interest, implied volatility (IV), Greeks from `quote_bulk`.
- **Compensation:**
  - **OTM%** instead of delta for strike selection (CSP 3–20%, CC 2–15%).
  - **Spread width** (max 25%) for liquidity/execution quality.
  - **Bid/min credit** for minimum premium.
  - Scoring uses premium, DTE, spread, OTM, and liquidity only (no delta/IV weights).

### Pre-Trade Checklist

Before executing any selected signal:

1. **Earnings date** — No earnings in the option’s DTE window.
2. **Major news / events** — No FDA, M&A, or macro events that could move the underlying.
3. **Position sizing** — ≤ 5% per underlying; total CSP exposure ≤ 30% of buying power.
4. **Sector diversification** — Respect `guardrails.max_trades_per_sector` (e.g. max 3 per sector) when sector data is available.

---

## 1. Strategy Filter Validation

### Test Results Summary

| Ticker | Total Contracts | PUTs | CALLs | CSP Candidates | Pass |
|--------|----------------|------|-------|----------------|------|
| AAPL   | 968            | 484  | 484   | 352            | ✓    |
| MSFT   | 1,294          | 647  | 647   | 539            | ✓    |
| NVDA   | 940            | 470  | 470   | 384            | ✓    |
| TSLA   | 1,950          | 975  | 975   | 847            | ✓    |

### Rejection Breakdown (AAPL Example)

| Rejection Reason    | Count | Description |
|---------------------|-------|-------------|
| `no_bid`            | 56    | No bid price available |
| `bid_too_low`       | 43    | Bid below $0.05 minimum |
| `spread_too_wide`   | 26    | Bid-ask spread > 25% |
| `credit_too_low`    | 7     | Credit below $0.10 minimum |
| `no_delta`          | 359   | Delta not available (expected for Standard) |

**Note:** Delta is NOT available via `quote_bulk` endpoint for Standard subscriptions.

---

## 2. End-to-End Pipeline Results

```
Pipeline complete:
  Data source: live
  Symbols with options: 46
  Candidates: 259
  Selected: 10
  Gate: ALLOWED
```

**Status:** ✓ Pipeline is working correctly with live data.

---

## 3. CSP/CC Selection Logic

### Selection Logic Summary

- **DTE range:** 7–45 days to expiration.
- **OTM%:** CSP 3–20%, CC 2–15% (by underlying price).
- **Min credit / bid:** Bid ≥ $0.01; effective min credit ~$0.10.
- **Max spread:** Bid-ask spread ≤ 25%.
- **Delta and open interest:** Not available for Standard subscriptions (`quote_bulk`); selection uses OTM% only; OI filter is skipped when OI is N/A.

### Base Configuration (All Strategies)

| Parameter           | Value   | Description |
|---------------------|---------|-------------|
| `dte_min`           | 7       | Minimum days to expiration |
| `dte_max`           | 45      | Maximum days to expiration |
| `min_bid`           | $0.01   | Minimum bid price |
| `min_open_interest` | 50      | Minimum open interest (skipped if N/A) |
| `max_spread_pct`    | 25%     | Maximum bid-ask spread |

### Cash-Secured Put (CSP) Configuration

| Parameter      | Value     | Description |
|----------------|-----------|-------------|
| `otm_pct_min`  | 3%        | Minimum out-of-the-money percentage |
| `otm_pct_max`  | 20%       | Maximum out-of-the-money percentage |
| `delta_min`    | None      | Optional delta minimum (absolute value) |
| `delta_max`    | None      | Optional delta maximum (absolute value) |

**Selection Path:** OTM percentage-based (since delta not configured)

**Formula:** `OTM% = (Underlying Price - Strike) / Underlying Price`

For a PUT to be selected:
1. Strike must be below underlying price (OTM)
2. OTM% must be between 3% and 20%
3. Bid must be ≥ $0.01
4. Spread must be ≤ 25%

### Covered Call (CC) Configuration

| Parameter      | Value     | Description |
|----------------|-----------|-------------|
| `otm_pct_min`  | 2%        | Minimum out-of-the-money percentage |
| `otm_pct_max`  | 15%       | Maximum out-of-the-money percentage |
| `delta_min`    | None      | Optional delta minimum |
| `delta_max`    | None      | Optional delta maximum |

**Selection Path:** OTM percentage-based (since delta not configured)

**Formula:** `OTM% = (Strike - Underlying Price) / Underlying Price`

For a CALL to be selected:
1. Strike must be above underlying price (OTM)
2. OTM% must be between 2% and 15%
3. Bid must be ≥ $0.01
4. Spread must be ≤ 25%

---

## 4. Data Quality Caveats

### Standard Subscription Limitations

The `quote_bulk` endpoint (recommended for Standard subscriptions) provides:
- ✓ Bid/Ask prices
- ✓ Timestamp
- ✗ **Delta** (not included)
- ✗ **Gamma, Theta, Vega** (not included)
- ✗ **Open Interest** (not included)
- ✗ **Implied Volatility** (not included)

**Impact:**
- Delta-based selection is **disabled** (falls back to OTM%)
- Open interest filtering is **skipped** when OI = None
- IV-based scoring components may be zero

### Recommended Mitigations

1. **Use OTM% instead of Delta** — The current configuration uses OTM percentage which doesn't require delta data.

2. **Adjust min_open_interest** — Since OI is not available, the filter is skipped. Consider other liquidity checks.

3. **Consider ohlc_bulk** — May provide additional data fields, though typically similar to quote_bulk for Standard.

---

## 5. Slack Integration

**Status:** Not configured

Slack alerts require the `SLACK_WEBHOOK_URL` environment variable:

```bash
# Windows
set SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Linux/Mac
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

When configured, alerts are sent automatically after each pipeline run.

---

## 6. Risk Guardrails & Recommendations

### Pre-Execution Checks (REQUIRED)

Before executing any signals, manually verify:

1. **No Earnings Events**
   - Check if the underlying has earnings within the option's DTE window
   - Earnings can cause extreme price movements
   - Tools: earnings calendars, company IR pages

2. **No Major News/Events**
   - FDA decisions, product launches, legal rulings
   - M&A announcements
   - Macro events (FOMC, CPI, employment data)

3. **Position Sizing**
   - Never allocate more than 5% of portfolio to a single underlying
   - Keep total CSP exposure below 30% of buying power
   - Account for margin requirements

4. **Market Conditions**
   - Check VIX level (elevated VIX = higher premiums but higher risk)
   - Avoid opening positions during high volatility events
   - Consider market direction/trend

### Additional Guardrails (RECOMMENDED)

| Guardrail | Description | Implementation |
|-----------|-------------|----------------|
| **Stop-Loss** | Exit if underlying drops X% below CSP strike | Manual or broker automation |
| **Profit Target** | Close at 50-75% of max profit | Manual monitoring |
| **DTE Exit** | Close positions 7-14 days before expiration | Time-based alerts |
| **News Screening** | Filter out symbols with recent news | External API integration |
| **Fundamental Filter** | Avoid symbols with poor fundamentals | Add data source |
| **Sector Diversification** | Limit exposure per sector | Position tracking |
| **Correlation Check** | Avoid highly correlated positions | Portfolio analysis |

### Scoring Weights (Phase 4A)

Scoring uses premium (credit), DTE, spread, OTM, and liquidity. For Standard subscriptions, delta and IV are not available from `quote_bulk`, so the configured weights emphasize credit, DTE, and liquidity:

```python
ScoringConfig(
    premium_weight=0.50,    # Credit / premium received (50%)
    dte_weight=0.25,        # Time value (25%)
    liquidity_weight=0.25,   # Liquidity (25%)
    spread_weight=0.0,     # Spread (0 when not differentiating)
    otm_weight=0.0,         # OTM (0 when using OTM% for selection only)
)
```

**Note:** Delta and open interest are unavailable for Standard subscriptions; selection is OTM%-based and OI filtering is skipped.

---

## 7. Validation Checklist

- [x] Bulk endpoints return live data
- [x] Strategy filters produce candidates (259 total)
- [x] Signals are selected (10 selected)
- [x] Gate is ALLOWED
- [x] Dashboard displays data without errors
- [ ] Slack alerts (not configured - optional)
- [ ] Earnings calendar check (manual, pre-execution)
- [ ] Position sizing verification (manual, pre-execution)

---

## 8. Quick Reference

### Test Commands

```bash
# Test single ticker with strategy validation
python scripts/test_orats_chain.py AAPL --validate-strategy

# Run full pipeline test
python scripts/run_and_save.py --test

# Run realtime mode (continuous updates)
python scripts/run_and_save.py --realtime --interval 60

# Start dashboard
python scripts/live_dashboard.py
```

### Configuration Files

- `config.yaml` — Main configuration (endpoint, timeouts, retention)
- `app/signals/engine.py` — Strategy parameters (hardcoded in run_and_save.py)
- `app/core/settings.py` — Settings loader

---

**Document Version:** 1.0  
**Last Updated:** 2026-01-30  
**Author:** ChakraOps Strategy Validation
