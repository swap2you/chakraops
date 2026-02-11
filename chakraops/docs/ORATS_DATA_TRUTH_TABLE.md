# ORATS Data Truth Table

**Single source of truth for ChakraOps ↔ ORATS field and endpoint mapping.**  
Validation-only document. No business logic changes.

---

| Stage | Purpose | ChakraOps Field | ORATS Endpoint | ORATS Field(s) | Required? | Used In Calculation? | If Missing |
|-------|---------|-----------------|----------------|----------------|-----------|----------------------|------------|
| Stage 1 | Equity Quote | stock.price (snapshot.price) | /datav2/strikes/options | stockPrice | YES | Eligibility gate | BLOCK |
| Stage 1 | Liquidity | stock.bid (snapshot.bid) | /datav2/strikes/options | bid | YES | Liquidity check | BLOCK |
| Stage 1 | Liquidity | stock.ask (snapshot.ask) | /datav2/strikes/options | ask | YES | Liquidity check | BLOCK |
| Stage 1 | Liquidity | stock.volume (snapshot.volume) | /datav2/strikes/options | volume | YES | Liquidity check | BLOCK |
| Stage 1 | Quote time | quote_date | /datav2/strikes/options | quoteDate | YES | Staleness gate | BLOCK |
| Stage 1 | IV Rank | iv_rank | /datav2/ivrank | ivRank1m (fallback ivPct1m) | YES | Volatility regime | BLOCK |
| Stage 2 | Options Chain | option bid/ask (per contract) | /datav2/live/strikes | bidPrice, askPrice (per option row) | YES | Strategy scoring, liquidity | BLOCK |
| Stage 2 | Options Chain | expirations, strikes | /datav2/live/strikes | expirDate, strike, optionSymbol | YES | Chain discovery | BLOCK |
| Optional | Stock volume today | stock_volume_today | /datav2/cores | stkVolu | NO | Filters only | IGNORE |
| Optional | Avg Option Volume | avg_option_volume_20d | /datav2/cores | avgOptVolu20d | NO | Filters only | IGNORE |
| Optional | Avg Stock Volume | avg_stock_volume_20d | /datav2/hist/dailies | stockVolume (mean last 20 rows) | NO | Filters only | IGNORE |
| Stage 2 (OPRA) | Option liquidity | bid/ask per OCC symbol | /datav2/strikes/options | bidPrice, askPrice (OCC symbols only) | When used | Liquidity validation | N/A (options path) |
| Future | Earnings | earnings_date | /datav2/live/summaries or cores | earnings / nextErn | NO | Not fully implemented | IGNORE |
| Future | News | news | — | — | NO | Not implemented | IGNORE |

---

## Endpoint base

- **Delayed / Stage 1:** `https://api.orats.io/datav2` → `/strikes/options`, `/ivrank`
- **Core / optional:** same base → `/cores`, `/hist/dailies`
- **Live / Stage 2:** same base → `/live/strikes`, `/live/summaries`

## Notes

1. **Stage 1 equity quote** is **only** from delayed `/datav2/strikes/options` (underlying rows). Live paths are forbidden for equity bid/ask/volume/iv_rank (data_requirements.py).
2. **Stage 2** chain and strategy scoring use `/datav2/live/strikes`; option rows have `bidPrice`, `askPrice`, `volume`, `openInterest`, etc.
3. **/datav2/strikes/options** is also used with **OCC option symbols only** (not underlying) for OPRA liquidity enrichment; underlying tickers must not be passed there for that call.
4. **quote_date** is used for staleness: if older than `STAGE1_STALE_TRADING_DAYS` (1), Stage 1 BLOCKs.
