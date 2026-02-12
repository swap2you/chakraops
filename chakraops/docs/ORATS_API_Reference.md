# ORATS API Reference for ChakraOps

Comprehensive reference derived from [ORATS_API_Reference_ChakraOps_Final.docx](ORATS_API_Reference_ChakraOps_Final.docx) and ORATS official documentation. Includes endpoints, parameters, example requests, and expected responses.

---

## 1. Overview

| API Family   | Base URL                    | Delay        | Use Case                                           |
|--------------|-----------------------------|--------------|----------------------------------------------------|
| **Live**     | `https://api.orats.io/datav2/live`       | <10 seconds  | Real-time option chains, summaries                 |
| **Live Derived** | `https://api.orats.io/datav2/live/derived` | <10 seconds  | Live without OPRA (bid/ask/volume null)           |
| **Delayed**  | `https://api.orats.io/datav2`            | 15 minutes   | Equity quotes, IV rank, per-contract option data   |
| **Historical** | `https://api.orats.io/datav2/hist`     | EOD          | Backtest, historical strikes                       |

**Authentication:** All requests require `token=<ORATS_API_TOKEN>` as a query parameter.

**Response envelope:** Every endpoint returns `{"data": [ ... ]}`. Payload is in the `data` array.

**Multi-ticker limit:** Max **10 tickers** per request. Batch larger lists.

---

## 2. Authentication

```bash
# Every request includes token
curl "https://api.orats.io/datav2/ivrank?token=YOUR_API_TOKEN&ticker=AAPL"
```

Set `ORATS_API_TOKEN` in environment or app config.

---

## 3. ChakraOps-Critical Endpoints

### 3.1 Delayed Strikes (Base Chain)

**Use:** Chain structure (strikes, expirations). Stage-2 DELAYED pipeline Step 1.

| Item   | Value                                                                 |
|--------|-----------------------------------------------------------------------|
| **Path** | `GET /datav2/strikes`                                                |
| **Base** | `https://api.orats.io/datav2`                                        |
| **Params** | `ticker` (required, comma-delimited, max 10), `dte`, `delta`, `fields` |

**Example request:**

```bash
curl -L "https://api.orats.io/datav2/strikes?token=my-token&ticker=AAPL&dte=30,45"
```

**Example response (truncated):**

```json
{
  "data": [
    {
      "ticker": "AAPL",
      "tradeDate": "2019-12-23",
      "expirDate": "2019-12-27",
      "dte": 5,
      "strike": 180,
      "stockPrice": 283.8,
      "callBidPrice": 103.7,
      "callAskPrice": 103.9,
      "putBidPrice": 0,
      "putAskPrice": 0.01,
      "callOpenInterest": 0,
      "putOpenInterest": 7,
      "delta": 1,
      "smvVol": 0.201089,
      "updatedAt": "2019-12-23T18:49:36Z"
    }
  ]
}
```

**Note:** `/strikes` returns combined call/put rows per strike. For per-contract `option_type`, bid, ask, OI, use `/strikes/options` with OCC symbols.

---

### 3.2 Delayed Strikes by OPRA (Per-Option + Equity Quote)

**Use:** Per-option liquidity (bid, ask, delta, OI) and equity quote for underlyings. Stage-2 DELAYED pipeline Step 3.

| Item   | Value                                                                 |
|--------|-----------------------------------------------------------------------|
| **Path** | `GET /datav2/strikes/options`                                        |
| **Params** | `tickers` (required): OCC symbols OR underlying tickers, comma-delimited, max 10 |

**OCC symbol format:** `{ROOT6}{YYMMDD}{P|C}{STRIKE*1000}`  
Example: `SPY  250321P00500000` = SPY Mar 21 2025 500 Put

**Example – Underlying tickers (equity quote):**

```bash
curl -L "https://api.orats.io/datav2/strikes/options?token=my-token&tickers=AAPL,MSFT"
```

**Example response (underlying row):**

```json
{
  "data": [
    {
      "ticker": "AAPL",
      "stockPrice": 274.97,
      "bid": 274.92,
      "ask": 275.01,
      "bidSize": 1,
      "askSize": 5,
      "volume": 1008510,
      "quoteDate": "2026-02-05T16:58:49Z",
      "updatedAt": "2026-02-05 16:59:11"
    }
  ]
}
```

**Example – OCC symbols (per-option):**

```bash
curl -L "https://api.orats.io/datav2/strikes/options?token=my-token&tickers=AAPL230915C00175000,VIXW230222P00020000"
```

**Example response (option row):**

```json
{
  "data": [
    {
      "ticker": "VIX",
      "optionSymbol": "VIXW230222P00020000",
      "tradeDate": "2023-02-03",
      "expirDate": "2023-02-22",
      "dte": 20,
      "strike": 20,
      "optionType": "Put",
      "stockPrice": 21.09,
      "volume": 0,
      "openInterest": 609,
      "bidPrice": 0.82,
      "askPrice": 1.01,
      "optValue": 0.91,
      "delta": 0.659823,
      "gamma": 0.101183,
      "theta": -0.0379109,
      "vega": 0.01705,
      "quoteDate": "2023-02-03T20:22:48Z",
      "updatedAt": "2023-02-03T20:22:58Z"
    }
  ]
}
```

**ChakraOps mapping:** `optionType` → PUT/CALL; `bidPrice`/`askPrice` → bid/ask; `openInterest` → OI.

---

### 3.3 Delayed IV Rank

**Use:** IV rank for Stage-1 regime (LOW/MID/HIGH).

| Item   | Value                                                                 |
|--------|-----------------------------------------------------------------------|
| **Path** | `GET /datav2/ivrank`                                                 |
| **Params** | `ticker` (optional, comma-delimited, max 10), `fields`               |

**Example request:**

```bash
curl -L "https://api.orats.io/datav2/ivrank?token=my-token&ticker=AAPL,MSFT"
```

**Example response:**

```json
{
  "data": [
    {
      "ticker": "AAPL",
      "tradeDate": "2023-11-03",
      "iv": 18.311,
      "ivRank1m": 0,
      "ivPct1m": 0,
      "ivRank1y": 17.49,
      "ivPct1y": 12.75,
      "updatedAt": "2023-11-03T20:55:02Z"
    }
  ]
}
```

**ChakraOps:** Prefer `ivRank1m`; fallback to `ivPct1m` if missing.

---

### 3.4 Live Strikes

**Use:** Live chain surface. **Important:** No per-contract `option_type`; rows are strike-level with `callBidPrice`/`putBidPrice` etc. ChakraOps Stage-2 uses DELAYED for per-contract PUT/CALL.

| Item   | Value                                                                 |
|--------|-----------------------------------------------------------------------|
| **Path** | `GET /datav2/live/strikes`                                           |
| **Params** | `ticker` (required)                                                  |

**Example request:**

```bash
curl "https://api.orats.io/datav2/live/strikes?token=my-token&ticker=AAPL"
```

**Example response (one row per strike, call+put columns):**

```json
{
  "data": [
    {
      "ticker": "AAPL",
      "tradeDate": "2023-11-03",
      "expirDate": "2023-11-17",
      "dte": 15,
      "strike": 142,
      "stockPrice": 176.78,
      "callBidPrice": 34.65,
      "callAskPrice": 35.2,
      "putBidPrice": 0.06,
      "putAskPrice": 0.07,
      "callOpenInterest": 1,
      "putOpenInterest": 11,
      "delta": 0.9977,
      "quoteDate": "2023-11-03T19:59:44Z",
      "updatedAt": "2023-11-03T19:59:57Z"
    }
  ]
}
```

---

### 3.5 Live Summaries

**Use:** Live SMV summaries, IVs, earnings. No equity bid/ask/volume.

| Item   | Value                                                                 |
|--------|-----------------------------------------------------------------------|
| **Path** | `GET /datav2/live/summaries`                                         |
| **Params** | `ticker` (optional)                                                  |

**Example request:**

```bash
curl -L "https://api.orats.io/datav2/live/summaries?token=my-token&ticker=AAPL"
```

**Example response (key fields):**

```json
{
  "data": [
    {
      "ticker": "AAPL",
      "tradeDate": "2023-11-03",
      "stockPrice": 176.78,
      "iv30d": 0.1858,
      "iv60d": 0.1922,
      "quoteDate": "2023-11-03T19:59:44Z",
      "updatedAt": "2023-11-03T20:00:29Z"
    }
  ]
}
```

---

### 3.6 Delayed Core Data

**Use:** Per-ticker snapshot: `avgOptVolu20d`, `ivRank`, `pxCls`, etc.

| Item   | Value                                                                 |
|--------|-----------------------------------------------------------------------|
| **Path** | `GET /datav2/cores`                                                  |
| **Params** | `ticker` (optional, comma-delimited, max 10), `fields`               |

**Example request:**

```bash
curl -L "https://api.orats.io/datav2/cores?token=my-token&ticker=AAPL"
```

---

## 4. Quick Reference: Which Endpoint for What

| Data needed                               | Endpoint                | Params                         | Constraint    |
|-------------------------------------------|-------------------------|--------------------------------|---------------|
| Equity quote (price, bid, ask, volume)    | `/strikes/options`      | `tickers=<underlying list>`    | 15 min delay  |
| IV rank                                   | `/ivrank`               | `ticker=<list>`                | 15 min delay  |
| Option chain base (delayed)               | `/strikes`              | `ticker`, `dte`, `delta`       | 15 min        |
| Per-option liquidity (bid, ask, OI, delta)| `/strikes/options`      | `tickers=<OCC symbols>`        | 15 min        |
| Live option chain                         | `/live/strikes`         | `ticker`                       | <10 s, no per-contract option_type |
| Live summaries (IV, etc.)                 | `/live/summaries`       | `ticker`                       | Live          |

---

## 5. ChakraOps Data Flow

1. **Stage 1:** `get_snapshot` uses delayed `/strikes/options` (underlyings) + `/cores` + `/ivrank`.
2. **Stage 2:** Uses DELAYED pipeline: `/strikes` → build OCC symbols → `/strikes/options` (OCC) → merge.  
   Rationale: DELAYED `/strikes/options` returns per-contract `optionType`, bid, ask, OI; LIVE `/live/strikes` does not.
3. **Phase 3 HOTFIX:** Stage-2 always uses DELAYED regardless of market phase.

---

## 6. Official ORATS Links

- [Delayed Data API](https://orats.com/docs/delayed-data-api)
- [Live Data API](https://orats.com/docs/live-data-api)
- [Authentication](https://orats.com/docs/authentication)
- [Field Definitions](https://orats.com/docs/definitions)
