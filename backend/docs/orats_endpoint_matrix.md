# ORATS Endpoint Matrix — ChakraOps Coverage

**Source:** Existing repo docs (ORATS_API_Reference.md, ORATS_DATAV2_ENDPOINT_AND_DATA_REFERENCE.md, ORATS_FIELD_TO_ENDPOINT_MAPPING.md). No web browse.

**Purpose:** Prove ORATS endpoint coverage and key fields; which phase uses each.

---

## 1. Delayed (15 min) — Stage-1 & Stage-2

| Endpoint | Path | Live vs delayed | Key fields returned | Works after hours? | ChakraOps phase |
|----------|------|-----------------|---------------------|--------------------|-----------------|
| Delayed strikes | `GET /datav2/strikes` | Delayed | ticker, expirDate, dte, strike, stockPrice, callBidPrice, putBidPrice, callAskPrice, putAskPrice, callOpenInterest, putOpenInterest, delta, smvVol | Unknown | Stage-2 (base chain) |
| Delayed strikes/options | `GET /datav2/strikes/options` | Delayed | **Underlying:** ticker, stockPrice, bid, ask, volume, quoteDate. **OCC (CONFIRMED by harness):** optionSymbol, ticker, expirDate, strike, optionType/putCall, bidPrice, askPrice, openInterest, delta, gamma, theta, vega, volume | Unknown | Stage-1 (equity quote); Stage-2 (per-contract liquidity) |
| Delayed ivrank | `GET /datav2/ivrank` | Delayed | ticker, ivRank1m, ivPct1m, ivRank1y, ivPct1y, iv | Unknown | Stage-1 (regime) |
| Delayed cores | `GET /datav2/cores` | Delayed | ticker, pxCls, stkVolu, avgOptVolu20d, ivRank, ivPctile1y, tradeDate, confidence, sector, marketCap | Unknown | Stage-1 (snapshot) |
| Delayed hist/dailies | `GET /datav2/hist/dailies` | EOD | stockVolume / stockVolu (for derived avg stock volume 20d) | Unknown | Stage-1 (derived avg_stock_volume_20d) |

---

## 2. Live — Not used for Stage-2 OPRA bid/ask

| Endpoint | Path | Live vs delayed | Key fields returned | Works after hours? | ChakraOps phase |
|----------|------|-----------------|---------------------|--------------------|-----------------|
| Live strikes | `GET /datav2/live/strikes` | Live | ticker, expirDate, dte, strike, stockPrice, callBidPrice, putBidPrice, callAskPrice, putAskPrice, delta, callOpenInterest, putOpenInterest; **no per-contract option_type** | Unknown | Future / alternate; Stage-2 uses DELAYED for per-contract |
| Live strikes/options | (if any) | Live | — | — | — |
| Live derived | `GET /datav2/live/derived` | Live | **Bid/ask/volume null** per ORATS docs | N/A | Do not use for Stage-2 |
| Live summaries | `GET /datav2/live/summaries` | Live | ticker, stockPrice, iv30d, iv60d, quoteDate; no equity bid/ask/volume | Unknown | Future: earnings/indicators |

---

## 3. Critical for Stage-2 (per-contract liquidity)

| Field | Status | Notes |
|-------|--------|-------|
| **optionSymbol** | CONFIRMED | Proven by harness (NVDA + SPY, delayed, 2026-02-12). |
| **strike, expirDate** | CONFIRMED | Identity; present in harness output. |
| **putCall / optionType** | CONFIRMED | PUT vs CALL; harness filtered PUTs. |
| **delta** | CONFIRMED | Non-null for all PUTs in DTE (NVDA 18/18, SPY 60/60). |
| **bidPrice, askPrice** | CONFIRMED | Non-null for all PUTs in DTE. |
| **openInterest** | CONFIRMED | Present for majority (NVDA 16/18, SPY 59/60); rare nulls. |

**Source endpoint:** Delayed `GET /datav2/strikes/options` with `tickers=<OCC symbols>` (max 10 per request). Do **not** use live/derived (returns null bid/ask).

---

## 4. How to verify “works after hours?”

- Run harness (e.g. `scripts/orats_harness.py --symbol NVDA --mode delayed`) when market is closed; check response rows and non-null counts for bidPrice, askPrice, openInterest.
- Document result in artifacts/orats_harness/ or runbook.
