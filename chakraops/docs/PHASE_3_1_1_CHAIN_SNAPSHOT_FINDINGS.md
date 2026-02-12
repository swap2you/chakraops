# Phase 3.1.1 – Chain snapshot implementation findings

Structured output from repository search for chain, expiration, strikes, option chain, 16:00, market close, EOD, end of day.

---

## 1. EOD **option chain** snapshot

**Conclusion: no dedicated EOD option chain snapshot implementation exists.**

- **Chain data** is always fetched **on-demand** when evaluation runs (Stage 2). No job persists option chain to disk at market close.
- **contract_data.source** is set to `"EOD_SNAPSHOT"` when market is closed in `build_eligibility_layers` (Phase 3.0.2); this is a **label only**. The same ORATS endpoints are used (delayed or live); there is no separate “EOD chain” storage or 16:00 capture.

```json
{
  "found": false,
  "files": [],
  "scheduler_trigger": "",
  "artifact_path": "",
  "endpoint": ""
}
```

---

## 2. EOD **stock** snapshot (exists; not option chain)

There **is** an EOD snapshot for **stock** daily bars (close, EMA, RSI, ATR) used by exit rules and market regime. It does **not** include option chain.

| Item | Value |
|------|--------|
| **File path** | `app/core/journal/eod_snapshot.py` |
| **Scheduler / trigger** | Called from `app/core/eval/nightly_evaluation.py` (exit rules with EOD snapshot); `app/core/market/market_regime.py` (get_eod_snapshot for SPY/QQQ). No dedicated “at 16:00” scheduler for this module. |
| **Artifact storage** | None. EODSnapshot is in-memory; built from daily bar DataFrame. No path like `artifacts/` or `out/` for EOD snapshot. |
| **Data source** | `YFinanceMarketDataAdapter.get_daily(symbol, lookback)` (default). Not ORATS. |

---

## 3. Option chain usage (no EOD snapshot)

| Item | Location / value |
|------|-------------------|
| **Chain discovery** | `app/core/options/orats_chain_pipeline.py`: STEP 1 → `/datav2/strikes` (base chain). `app/core/options/orats_chain_provider.py` uses `get_orats_live_strikes` → `/datav2/live/strikes`. |
| **Liquidity enrichment** | `app/core/options/orats_chain_pipeline.py`: STEP 3 → `/datav2/strikes/options` (OCC symbols only). `app/core/orats/endpoints.py`: `BASE_DATAV2`, `PATH_STRIKES`, `PATH_STRIKES_OPTIONS`, `PATH_LIVE_STRIKES`. |
| **ORATS endpoints** | Delayed: `https://api.orats.io/datav2` + `/strikes`, `/strikes/options`. Live: same base + `/live/strikes`. Mode via `ORATS_DATA_MODE` (orats_chain_pipeline.OratsDataMode). |
| **16:00 / market close** | `app/market/market_hours.py`: `MARKET_CLOSE = time(16, 0)` (9:30–16:00 ET). `scripts/run_and_save.py`: at “market close” writes **decision** snapshot `decision_{date}_end.json` (not option chain). |

---

## 4. Summary table

| Concept | Exists? | File(s) | Scheduler / trigger | Artifact path | Endpoint / source |
|--------|---------|---------|----------------------|---------------|-------------------|
| EOD **option chain** snapshot | **No** | — | — | — | — |
| EOD **stock** snapshot (daily bars) | Yes | `app/core/journal/eod_snapshot.py` | Nightly eval, market_regime | None (in-memory) | yfinance `get_daily` |
| Option chain (on-demand) | Yes | orats_chain_pipeline, orats_chain_provider, orats_client, orats_opra | Evaluation Stage 2 | None | ORATS `/datav2/strikes`, `/datav2/strikes/options`, `/datav2/live/strikes` |
| Decision snapshot at market close | Yes | `scripts/run_and_save.py` | Realtime loop until end_time (e.g. 16:00) | `output_dir/decision_{date}_end.json` | Pipeline output (not ORATS chain) |

---

**Bottom line:** There is no EOD **chain** snapshot implementation. To add one, you would need to introduce a scheduler (or reuse an existing one), a storage path for chain artifacts, and a choice of ORATS endpoint (e.g. delayed `/datav2/strikes` + `/datav2/strikes/options` at or after 16:00).
