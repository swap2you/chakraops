# ChakraOps Strategy Validation Report

**Generated:** 2026-01-30  
**Data Source:** ThetaData Terminal v3 (Bulk Endpoints)  
**Endpoint:** `quote_bulk`

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

The current scoring configuration:

```python
ScoringConfig(
    credit_weight=0.35,     # Premium received
    delta_weight=0.25,      # Risk level (0 if delta unavailable)
    iv_weight=0.20,         # Implied volatility value (0 if IV unavailable)
    dte_weight=0.10,        # Time value
    liquidity_weight=0.10,  # Volume/OI quality
)
```

**Recommendation:** Since delta and IV are not available from `quote_bulk`, consider adjusting weights:

```python
ScoringConfig(
    credit_weight=0.50,     # Increase credit importance
    delta_weight=0.00,      # Disable (data not available)
    iv_weight=0.00,         # Disable (data not available)
    dte_weight=0.25,        # Increase time value importance
    liquidity_weight=0.25,  # Increase liquidity importance
)
```

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
python scripts/test_theta_chain.py AAPL --validate-strategy

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
