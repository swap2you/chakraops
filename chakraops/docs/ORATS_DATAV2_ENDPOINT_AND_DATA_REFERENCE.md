# ORATS datav2: Endpoint & Data Reference

**Purpose:** Single reference for what endpoints orats-util (and downstream systems like ChakraOps) call, how to form queries, what data comes back, and what constraints apply. Use this instead of passing raw JSONs.

**Base URL:** `https://api.orats.io/datav2`  
**Authentication:** `token=<ORATS_API_TOKEN>` query parameter (required on every request).

---

## 1. Architecture Overview

- **orats-util** hits **8 ORATS datav2 endpoints**. Each run saves raw JSON under `out/<endpoint_name>/<date>/<time>/raw.json` and metadata in `meta.json`.
- **Response envelope:** Every endpoint returns `{"data": [ ... ]}`. All payload is in the `data` array (one object per row, or one row per ticker for summary-style endpoints).
- **Multi-ticker limit:** Endpoints that accept multiple tickers are capped at **10 tickers per request**. Batch larger lists into groups of 10.

---

## 2. Data Families & Constraints

| Family   | Constraint | Notes |
|----------|------------|--------|
| **Live** | &lt;10 seconds market delay | `stockPrice` may be derived from put-call parity and can differ from true equity quote until ~15 min. **Live endpoints do not return equity quote fields (bid, ask, volume)** for underlyings; use delayed for that. |
| **Delayed** | 15-minute delayed | All quote-like fields (bid, ask, volume, stockPrice, quoteDate) are 15 min delayed. |

**Important for ChakraOps:**

- **Equity quote fields (bid, ask, volume, stockPrice, quoteDate):** Use **delayed** `/strikes/options` with **underlying tickers** in `tickers=`. Only this endpoint returns `bid`, `ask`, `bidSize`, `askSize`, `volume`, `quoteDate` for stocks.
- **IV rank:** Use **delayed** `/ivrank` with `ticker=`. Returns `ivRank1m`, `ivPct1m`, `ivRank1y`, `ivPct1y`, `iv`.
- **avg_volume:** **Not provided** by any of these 8 endpoints. Do not fabricate; treat as missing if required.

---

## 3. Endpoints (What We Hit, What We Get)

---

### 3.1 `live_strikes` (Live)

| Item | Value |
|------|--------|
| **Path** | `GET /live/strikes` |
| **Constraint** | Live (&lt;10s delay). `stockPrice` may be put-call parity. |
| **Required params** | `ticker` (single underlying, e.g. AAPL) |
| **Optional params** | — |

**Query example:**
```
GET https://api.orats.io/datav2/live/strikes?token=...&ticker=AAPL
```

**Use for:** Full option chain surface by strike/expiry. Large payload.

**Response – fields (per row):**  
`ticker`, `tradeDate`, `expirDate`, `dte`, `strike`, `stockPrice`, `callVolume`, `putVolume`, `callBidPrice`, `callAskPrice`, `putBidPrice`, `putAskPrice`, `callValue`, `putValue`, `callBidIv`, `callMidIv`, `callAskIv`, `putBidIv`, `putMidIv`, `putAskIv`, `smvVol`, `residualRate`, `delta`, `gamma`, `theta`, `vega`, `rho`, `phi`, `driftlessTheta`, `extCallValue`, `extPutValue`, `extSmvVol`, `spotPrice`, `quoteDate`, `updatedAt`, `callOpenInterest`, `putOpenInterest`, `callBidSize`, `callAskSize`, `putBidSize`, `putAskSize`, `expiryTod`, `callSmvVol`, `putSmvVol`.

**Does not provide:** Equity-level bid/ask/volume for the underlying; those are option-level only.

---

### 3.2 `live_strikes_monthly` (Live)

| Item | Value |
|------|--------|
| **Path** | `GET /live/strikes/monthly` |
| **Constraint** | Same as live_strikes. |
| **Required params** | `ticker`, `expiry` (YYYY-MM-DD; comma-delimited for multiple) |
| **Optional params** | — |

**Query example:**
```
GET https://api.orats.io/datav2/live/strikes/monthly?token=...&ticker=AAPL&expiry=2026-02-20
```

**Use for:** Same as live_strikes but filtered to one or more expiries (smaller payload).

**Response – fields (per row):** Same shape as `live_strikes` (option chain rows). No equity quote fields for underlying.

---

### 3.3 `live_monies_implied` (Live)

| Item | Value |
|------|--------|
| **Path** | `GET /live/monies/implied` |
| **Constraint** | Live. |
| **Required params** | `ticker` |
| **Optional params** | — |

**Query example:**
```
GET https://api.orats.io/datav2/live/monies/implied?token=...&ticker=AAPL
```

**Use for:** Monthly implied monies – delta seed vol curves, rates, fit, earnings effect.

**Response – fields (per row):**  
`ticker`, `tradeDate`, `expirDate`, `expiryTod`, `stockPrice`, `spotPrice`, `riskFreeRate`, `yieldRate`, `residualYieldRate`, `residualRateSlp`, `residualR2`, `confidence`, `mwVol`, `vol100`…`vol0`, `typeFlag`, `atmiv`, `slope`, `deriv`, `fit`, `calVol`, `unadjVol`, `earnEffect`, `quoteDate`, `updatedAt`.

**Does not provide:** Equity bid/ask/volume.

---

### 3.4 `live_monies_forecast` (Live)

| Item | Value |
|------|--------|
| **Path** | `GET /live/monies/forecast` |
| **Constraint** | Live. |
| **Required params** | `ticker` |
| **Optional params** | — |

**Query example:**
```
GET https://api.orats.io/datav2/live/monies/forecast?token=...&ticker=AAPL
```

**Use for:** Forecast seed vol curves by delta.

**Response – fields (per row):**  
`ticker`, `tradeDate`, `expirDate`, `expiryTod`, `stockPrice`, `riskFreeRate`, `vol100`…`vol0`, `quoteDate`, `updatedAt`.

**Does not provide:** Equity bid/ask/volume.

---

### 3.5 `live_summaries` (Live)

| Item | Value |
|------|--------|
| **Path** | `GET /live/summaries` |
| **Constraint** | Live. |
| **Required params** | `ticker` |
| **Optional params** | — |

**Query example:**
```
GET https://api.orats.io/datav2/live/summaries?token=...&ticker=AAPL
```

**Use for:** SMV summary – interpolated IVs (iv10d, iv20d, iv30d, …), ex-earnings IVs, borrow rates, contango, implied move, earnings effect, delta-specific IVs (dlt5, dlt25, dlt75, dlt95), forward/flat forward metrics.

**Response – one row per ticker.** Fields include:  
`ticker`, `tradeDate`, `stockPrice`, `quoteDate`, `updatedAt`, `annActDiv`, `annIdiv`, `borrow30`, `borrow2y`, `confidence`, `contango`, `exErnIv10d`…`exErnIv1y`, `iv10d`…`iv1y`, `impliedMove`, `impliedEarningsMove`, `impliedNextDiv`, `nextDiv`, `rDrv30`, `rDrv2y`, `rSlp30`, `rSlp2y`, `rVol30`, `rVol2y`, `rip`, `riskFree30`, `riskFree2y`, `skewing`, `totalErrorConf`, `dlt5Iv10d`…, `dlt25Iv10d`…, `dlt75Iv10d`…, `dlt95Iv10d`…, `fwd30_20`, `fwd60_30`, etc., `ieeEarnEffect`, `mwAdj30`, `mwAdj2y`.

**Sample value (conceptually):**  
`stockPrice`: 274.12, `iv30d`: 0.247…, `quoteDate`: "2026-02-05T17:14:22Z".  
**Does not provide:** Equity bid/ask/volume; live summaries are derived metrics, not quote feeds.

---

### 3.6 `delayed_strikes` (Delayed, 15 min)

| Item | Value |
|------|--------|
| **Path** | `GET /strikes` |
| **Constraint** | 15-minute delayed. |
| **Required params** | `ticker` (comma-delimited, max 10) |
| **Optional params** | `fields`, `dte`, `delta` |

**Query example:**
```
GET https://api.orats.io/datav2/strikes?token=...&ticker=AAPL
GET https://api.orats.io/datav2/strikes?token=...&ticker=AAPL,MSFT&dte=30,45&delta=.30,.45
```

**Use for:** Delayed option chain; optional field filter and DTE/delta filters.

**Response – fields (per row):** Same idea as live_strikes (option-level). Additionally may include `snapShotDate`, `snapShotEstTime`. No equity-level bid/ask/volume for the underlying.

---

### 3.7 `delayed_strikes_options` (Delayed, 15 min) — **Source for equity quotes**

| Item | Value |
|------|--------|
| **Path** | `GET /strikes/options` |
| **Constraint** | 15-minute delayed. |
| **Required params** | `tickers` (comma-delimited: OCC option symbols **or underlying tickers**; max 10) |
| **Optional params** | — |

**Query example (underlying tickers – use this for equity quote data):**
```
GET https://api.orats.io/datav2/strikes/options?token=...&tickers=AAPL
GET https://api.orats.io/datav2/strikes/options?token=...&tickers=AAPL,MSFT,GOOGL,DIS
```

**Use for:**  
- **Underlying tickers only:** Authoritative **equity quote** data: `stockPrice`, `bid`, `ask`, `bidSize`, `askSize`, `volume`, `quoteDate`, `updatedAt`.  
- **OCC option symbols:** Per-option snapshot (optionSymbol, bidPrice, askPrice, optValue, greeks, etc.).  
- Mixed lists (underlyings + OCC symbols) return both row types; match by presence of `optionSymbol` (option row) vs its absence (underlying row).

**Response – when passing UNDERLYING tickers only (one row per ticker):**

| Field       | Type   | Sample / description |
|------------|--------|------------------------|
| `ticker`   | string | "AAPL" |
| `stockPrice` | number | 274.97 |
| `bid`      | number | 274.92 |
| `ask`      | number | 275.01 |
| `bidSize`  | number | 1 |
| `askSize`  | number | 5 |
| `volume`   | number | 1008510 |
| `quoteDate`| string | "2026-02-05T16:58:49Z" (ISO UTC) |
| `updatedAt`| string | "2026-02-05 16:59:11" |

**Mapping for ChakraOps (equity snapshot):**  
`stockPrice` → price, `bid` → bid, `ask` → ask, `volume` → volume, `quoteDate` → quote_time.  
**avg_volume:** Not in this response; leave missing.

**Sample raw row (underlying):**
```json
{"ticker":"AAPL","stockPrice":274.97,"bid":274.92,"ask":275.01,"bidSize":1,"askSize":5,"volume":1008510,"quoteDate":"2026-02-05T16:58:49Z","updatedAt":"2026-02-05 16:59:11"}
```

---

### 3.8 `delayed_ivrank` (Delayed, 15 min) — **Source for IV rank**

| Item | Value |
|------|--------|
| **Path** | `GET /ivrank` |
| **Constraint** | 15-minute delayed. |
| **Required params** | None (omit ticker = all tickers; can be huge) |
| **Optional params** | `ticker` (comma-delimited, max 10), `fields` |

**Query example:**
```
GET https://api.orats.io/datav2/ivrank?token=...&ticker=AAPL
GET https://api.orats.io/datav2/ivrank?token=...&ticker=AAPL,MSFT,GOOGL,DIS
```

**Use for:** IV rank / percentile. Prefer `ivRank1m`; if missing use `ivPct1m`.

**Response – one row per ticker:**

| Field     | Type   | Sample / description |
|----------|--------|------------------------|
| `ticker` | string | "AAPL" |
| `tradeDate` | string | "2026-02-05" |
| `iv`     | number | 25.008 (current IV level) |
| `ivRank1m` | number | 73.52 (IV rank over 1 month) |
| `ivPct1m`  | number | 90 (IV percentile 1m) |
| `ivRank1y` | number | 17.65 |
| `ivPct1y`  | number | 64.94 |
| `updatedAt` | string | "2026-02-05T17:10:03Z" |

**Mapping for ChakraOps:**  
`iv_rank` ← `ivRank1m` (preferred) or `ivPct1m` if `ivRank1m` absent.

**Sample raw row:**
```json
{"ticker":"AAPL","tradeDate":"2026-02-05","iv":25.008,"ivRank1m":73.52,"ivPct1m":90,"ivRank1y":17.65,"ivPct1y":64.94,"updatedAt":"2026-02-05T17:10:03Z"}
```

---

## 4. Quick Reference: Which Endpoint for What

| Data needed | Endpoint | Params | Constraint |
|-------------|----------|--------|------------|
| Equity quote (price, bid, ask, volume, quote_time) | `delayed_strikes_options` | `tickers=<underlying list>` (max 10) | 15 min delayed; use underlying rows only |
| IV rank (iv_rank) | `delayed_ivrank` | `ticker=<list>` (max 10) | 15 min delayed; use ivRank1m or ivPct1m |
| Option chain (delayed) | `delayed_strikes` | `ticker`, optional `fields`, `dte`, `delta` | 15 min; max 10 tickers |
| Option chain (live) | `live_strikes` or `live_strikes_monthly` | `ticker`, monthly needs `expiry` | Live &lt;10s; no equity quote |
| Summary IVs / earnings / borrow (live) | `live_summaries` | `ticker` | Live; no bid/ask/volume |
| Implied monies (live) | `live_monies_implied` | `ticker` | Live |
| Forecast monies (live) | `live_monies_forecast` | `ticker` | Live |
| Per-option snapshot (by OCC symbol) | `delayed_strikes_options` | `tickers=<OCC symbols>` | 15 min |

---

## 5. What Is Not Available (Do Not Fabricate)

- **avg_volume:** Not returned by any of the 8 endpoints. Leave as missing and report; do not invent.
- **Equity bid/ask/volume from live endpoints:** Live endpoints do not return equity-level quote fields; only delayed `/strikes/options` with underlying tickers does.
- **Real-time equity quote:** Delayed endpoints are 15 min behind; live endpoints do not provide underlying bid/ask/volume.

---

## 6. orats-util Output Layout

- **Location:** `out/<endpoint_name>/<YYYY-MM-DD>/<HHMMSS>/`
- **Files:** `raw.json` (full API response), `meta.json` (fetched_at, http_status, bytes, request_url redacted, top_level_keys, first_row_keys, data_len).
- **Usage:** This reference doc describes the same endpoints and fields; ChakraOps can rely on this instead of parsing all raw JSONs.

---

## 7. ORATS Official Docs (Links Only)

- Delayed Data API: https://orats.com/docs/delayed-data-api  
- Live Data API: https://orats.com/docs/live-data-api  
- Authentication: https://orats.com/docs/authentication  
- Field definitions: https://orats.com/docs/definitions  
