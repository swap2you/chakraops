# ORATS Option Data Pipeline – Architecture

## Overview

This document describes the ORATS data ingestion architecture for ChakraOps. The system uses multiple ORATS endpoints to fetch:

1. **Equity quotes** (price, bid, ask, volume) from `/datav2/strikes/options` with underlying tickers
2. **IV rank** from `/datav2/ivrank`
3. **Option chains** from `/datav2/strikes` or `/datav2/live/strikes`
4. **Option liquidity** from `/datav2/strikes/options` with OCC option symbols

---

## ORATS Endpoint Reference

| Endpoint | Purpose | Params | Returns |
|----------|---------|--------|---------|
| `/datav2/strikes/options` | Equity quotes (underlying tickers) | `tickers=AAPL,MSFT,...` (up to 10) | stockPrice, bid, ask, volume, quoteDate |
| `/datav2/strikes/options` | Option liquidity (OCC symbols) | `tickers=AAPL260320P00175000,...` (up to 10) | bidPrice, askPrice, volume, openInterest, greeks |
| `/datav2/ivrank` | IV rank data | `ticker=AAPL,MSFT,...` (up to 10) | ivRank1m, ivPct1m |
| `/datav2/strikes` | Option chain discovery | `ticker=AAPL` | strike grid (expirDate, strike, dte, delta) |
| `/datav2/live/strikes` | Live option chain | `ticker=AAPL` | strike grid with live pricing |

**Multi-ticker limit:** All multi-ticker endpoints are capped at **10 tickers per request**. Batching is automatic.

---

## Equity Snapshot Ingestion

Equity-level fields for evaluation, scoring, and UI are sourced from **two** ORATS endpoints:

### 1. Equity Quotes from `/datav2/strikes/options`

The `/datav2/strikes/options` endpoint accepts **underlying tickers** and returns equity quote data.

**Request:**
```
GET https://api.orats.io/datav2/strikes/options?token=...&tickers=AAPL,MSFT,GOOGL
```

**Response contains underlying rows with:**
- `ticker` - Symbol
- `stockPrice` - Current stock price
- `bid` - Underlying bid
- `ask` - Underlying ask
- `bidSize` - Bid size
- `askSize` - Ask size
- `volume` - Trading volume
- `quoteDate` - Quote timestamp

### 2. IV Rank from `/datav2/ivrank`

**Request:**
```
GET https://api.orats.io/datav2/ivrank?token=...&ticker=AAPL,MSFT,GOOGL
```

**Response contains:**
- `ticker` - Symbol
- `ivRank1m` - 1-month IV rank (preferred)
- `ivPct1m` - 1-month IV percentile (fallback)

### Field Mapping

| Internal Field | ORATS Endpoint | ORATS Key | Notes |
|----------------|----------------|-----------|-------|
| `price` | `/strikes/options` | `stockPrice` | Required for evaluation |
| `bid` | `/strikes/options` | `bid` | Underlying bid |
| `ask` | `/strikes/options` | `ask` | Underlying ask |
| `volume` | `/strikes/options` | `volume` | Trading volume |
| `quote_date` | `/strikes/options` | `quoteDate` | Quote timestamp |
| `iv_rank` | `/ivrank` | `ivRank1m` or `ivPct1m` | 1-month IV rank |
| `avg_volume` | — | — | **NOT AVAILABLE** from ORATS |

### Data Source Tracking

Each evaluation result includes:
- `data_sources`: Dict mapping field name → endpoint that provided it
- `raw_fields_present`: List of ORATS keys that were present in response
- `missing_fields`: List of fields that were not available
- `missing_reasons`: Dict mapping field → reason it's missing

Example:
```json
{
  "data_sources": {
    "price": "strikes/options",
    "bid": "strikes/options",
    "ask": "strikes/options",
    "volume": "strikes/options",
    "iv_rank": "ivrank"
  },
  "raw_fields_present": ["stockPrice", "bid", "ask", "volume", "quoteDate", "ivRank1m"],
  "missing_fields": ["avg_volume"],
  "missing_reasons": {
    "avg_volume": "Not available from ORATS endpoints"
  }
}
```

---

## Option Chain Pipeline

For option liquidity validation, the pipeline follows these steps:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     ORATS OPTION DATA PIPELINE                               │
└─────────────────────────────────────────────────────────────────────────────┘

  [1] CHAIN DISCOVERY
      GET /datav2/strikes  OR  GET /datav2/live/strikes
      Param: ticker (underlying only, e.g. AAPL)
      Output: Strike grid (expirDate, strike, dte, delta, stockPrice, …)
      No liquidity data at this step.
              │
              ▼
  [2] CONTRACT SELECTION
      From chain rows: select bounded set (e.g. max N expiries × M strikes).
      Filter by DTE, moneyness, etc. Produces list of (symbol, expiration, strike, type).
              │
              ▼
  [3] OCC CONSTRUCTION
      For each selected contract, build OCC symbol:
        ROOT + YYMMDD + C|P + STRIKE*1000 (8 digits)
      Example: AAPL 2026-03-20 Put 175 → "AAPL260320P00175000"
      Invariant: every symbol passed to step 4 must pass is_occ_option_symbol().
              │
              ▼
  [4] OPRA LOOKUP
      GET /datav2/strikes/options
      Param: tickers (PLURAL) = comma-separated OCC symbols.
      Output: Option rows with optionSymbol, bidPrice, askPrice, volume, openInterest, greeks.
              │
              ▼
  [5] LIQUIDITY VALIDATION
      Only after OPRA response: treat a contract as having valid liquidity when
      bid/ask (and optionally OI) exist. "ORATS OK" in logs only when at least
      one contract has bid/ask.
```

---

## Module Roles

| Module | Responsibility |
|--------|----------------|
| `app.core.orats.orats_equity_quote` | Equity quotes from `/strikes/options` (underlying tickers) and IV rank from `/ivrank`. Handles batching (10 tickers max), caching, and field mapping. |
| `app.core.orats.orats_opra` | Option liquidity from `/strikes/options` (OCC symbols). Chain discovery from `/strikes`. OCC symbol construction. |
| `app.core.orats.orats_client` | Live endpoints (`/live/strikes`, `/live/summaries`) |
| `app.core.options.orats_chain_pipeline` | Full pipeline: chain → OCC → OPRA → merge |
| `app.core.eval.staged_evaluator` | Stage 1 (stock quality) uses `orats_equity_quote`; Stage 2 (chain) uses pipeline |

---

## Caching

- Equity quotes and IV ranks are cached per evaluation run
- Cache is keyed by symbol (case-insensitive)
- Cache is reset at the start of each evaluation run via `reset_run_cache()`
- Batches are tracked to prevent duplicate API calls for the same tickers

---

## Missing Fields Handling

### avg_volume

The `avg_volume` field is **never available** from ORATS endpoints. It will always be in `missing_fields` with reason "Not available from ORATS endpoints".

If average volume is required, an external data source must be integrated.

### Other Missing Fields

If ORATS returns a response but certain fields are missing:
- The field is set to `None`
- It's added to `missing_fields`
- Reason is recorded in `missing_reasons` (e.g., "Not in ORATS response")

---

## Error Handling

- **HTTP errors**: Raise `OratsEquityQuoteError` with status code and details
- **Missing ticker rows**: Create entries with `error` field set
- **Rate limiting**: Built-in rate limiter (5 calls/second)
- **Timeouts**: 15-second timeout per request

---

## UI Display Guidelines

| Field Status | UI Display | Notes |
|--------------|------------|-------|
| Value present | Show value | e.g., `$275.45`, `45M vol` |
| Value `None` + ORATS returned no data | "N/A" | Show reason from `missing_reasons` |
| Value `None` + avg_volume | "N/A (not from ORATS)" | Always missing |
| Waiver active (OPRA liquidity confirmed) | "WAIVED" | Tooltip explains OPRA authority |

---

## Downstream Consumers

- **Evaluation gates:** Stage 1 uses `price` (required), `bid`, `ask`, `volume`, `iv_rank`. Missing `avg_volume` does not block evaluation.
- **Scoring:** Data completeness considers all fields; missing fields reduce completeness score.
- **UI:** Symbol cards show fields when present; `quote_date` displayed for transparency.
- **Alerts:** Use evaluation verdict, not raw snapshot fields.

---

## Data Flow Through Evaluation Pipeline

The equity quote data flows through the evaluation pipeline as follows:

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW DIAGRAM                                     │
└────────────────────────────────────────────────────────────────────────────────┘

1. ORATS Endpoints → FullEquitySnapshot (orats_equity_quote.py)
   ├── /datav2/strikes/options (underlying) → price, bid, ask, volume, quote_date
   └── /datav2/ivrank → iv_rank

2. FullEquitySnapshot → Stage1Result (staged_evaluator.py)
   └── All fields copied: price, bid, ask, volume, avg_volume (None), iv_rank

3. Stage1Result → FullEvaluationResult (staged_evaluator.py)
   └── All fields copied: price, bid, ask, volume, avg_volume

4. FullEvaluationResult → SymbolEvaluationResult (universe_evaluator.py)
   └── All fields copied: price, bid, ask, volume, avg_volume

5. SymbolEvaluationResult → Evaluation JSON (evaluation_store.py)
   └── All fields serialized: price, bid, ask, volume, avg_volume
```

### Field Propagation Checklist

| Field | FullEquitySnapshot | Stage1Result | FullEvaluationResult | SymbolEvaluationResult | JSON |
|-------|-------------------|--------------|---------------------|----------------------|------|
| price | ✓ | ✓ | ✓ | ✓ | ✓ |
| bid | ✓ | ✓ | ✓ | ✓ | ✓ |
| ask | ✓ | ✓ | ✓ | ✓ | ✓ |
| volume | ✓ | ✓ | ✓ | ✓ | ✓ |
| avg_volume | None | None | None | None | null |
| iv_rank | ✓ | ✓ | (via stage1) | (via stage1) | ✓ |
| quote_date | ✓ | ✓ | ✓ | — | ✓ |
| data_sources | ✓ | ✓ | ✓ | — | ✓ |

### Important Notes

1. **avg_volume** is NEVER available from ORATS. It will always be `None` / `null`.

2. The data flows through multiple dataclass types:
   - `FullEquitySnapshot` (raw ORATS data)
   - `Stage1Result` (stage 1 evaluation)
   - `FullEvaluationResult` (full 2-stage evaluation)
   - `SymbolEvaluationResult` (universe evaluation)

3. All types now have `bid`, `ask`, `volume`, `avg_volume` fields that are properly propagated.

4. The `to_dict()` methods serialize all equity fields for API responses and JSON persistence.
