# CSP/CC Candidate Evaluation — Signal Contract Audit

This document is a factual, code-referenced audit of the current CSP candidate evaluation logic: where signals come from, which inputs are used, and what is missing relative to an options-Greeks-based strategy.

---

## 1. Code path that produces CSP candidates in the heartbeat

**Entry:** `HeartbeatManager._evaluate_cycle()` in `app/core/heartbeat.py` (approx. lines 266–447).

**Flow:**

1. **Regime:** `_get_regime_with_age()` → `get_latest_regime()` from DB (`app.core.persistence`). Regime is one of `RISK_ON` / `RISK_OFF` (mapped from BULL/BEAR/NEUTRAL/UNKNOWN).
2. **Universe:** `get_enabled_symbols()` from `app.core.persistence` → symbols with `enabled=1` in `symbol_universe`.
3. **Snapshot:** `get_active_snapshot()` then `load_snapshot_data(snapshot_id)` from `app.core.market_snapshot` → per-symbol DataFrames (OHLCV-style).
4. **Price/volume/IV for scoring:** `get_snapshot_prices(snapshot_id)` (`app/core/market_snapshot.py`, ~1023–1085) → for each symbol: `price`, `volume`, `iv_rank` (all optional floats).
5. **Per-symbol eligibility/score:** For each symbol in the evaluation set, the heartbeat calls  
   `self.evaluate_csp_symbol(symbol, price, volume, iv_rank, regime, data_stale_minutes, universe_metadata)`  
   (heartbeat ~474–494, implementation ~746–954).
6. **Persistence of evaluations:** `upsert_csp_evaluations(snapshot_id, evaluations)` (`app.core.persistence`).
7. **Legacy candidate list:** `find_csp_candidates(symbol_to_df, regime)` from `app.core.wheel` (~408–413), where `symbol_to_df` is the same snapshot DataFrames keyed by symbol. No `orats_client` is passed, so no options chain is fetched in the heartbeat path.
8. **Assignment scoring:** For each candidate, `score_assignment_worthiness(candidate, regime)` from `app.core.assignment_scoring` (~419–423).

So the pipeline that actually drives “CSP candidates” in the heartbeat uses:

- **Snapshot** as the sole market-data source (DB-stored snapshot built from CSV/CACHE).
- **Regime** from `market_regimes`.
- **Universe** from `symbol_universe` (enabled symbols).
- **Evaluator:** `HeartbeatManager.evaluate_csp_symbol()` (price, volume, iv_rank, regime, snapshot_age_minutes, universe_metadata).
- **Candidate filter:** `find_csp_candidates(symbol_to_df, regime)` (stock-only in this call path).
- **Assignment layer:** `score_assignment_worthiness(candidate, regime)`.

---

## 2. Signals used today (with file references)

| Signal | Source | Where it is produced / read | Used in |
|--------|--------|-----------------------------|--------|
| **price** | Snapshot | `get_snapshot_prices()` reads `load_snapshot_data()`; for each symbol, last row: `close` or `price` → `data["price"]` (`market_snapshot.py` ~1054–1062) | `evaluate_csp_symbol(price=...)`; `find_csp_candidates` uses OHLCV from same snapshot |
| **volume** | Snapshot | Same `get_snapshot_prices()`: column `volume`, last row → `data["volume"]` (~1064–1068) | `evaluate_csp_symbol(volume=...)` |
| **iv_rank** | Snapshot | Same: column `iv_rank` (if present), last row → `data["iv_rank"]` (~1070–1075). Column `iv` is not used to set `iv_rank` | `evaluate_csp_symbol(iv_rank=...)` |
| **regime** | DB | `get_latest_regime()` → `market_regimes.regime`; heartbeat maps BULL/NEUTRAL→RISK_ON, BEAR/UNKNOWN→RISK_OFF (`heartbeat.py` ~277–325, ~451) | `evaluate_csp_symbol(regime=...)`, `find_csp_candidates(regime=...)`, `score_assignment_worthiness(..., regime)` |
| **snapshot_age_minutes** | Snapshot metadata | `snapshot.get("data_age_minutes", 0.0)` from active snapshot (~435) | `evaluate_csp_symbol(snapshot_age_minutes=...)` |
| **universe_metadata** | DB | `list_universe_symbols()` → `symbol_universe` (enabled, notes); normalized and passed as `universe_metadata_map` (~456–466) | `evaluate_csp_symbol(universe_metadata=...)` for priority/tier (docstring ~529–530; tier/priority logic ~891–906) |
| **OHLCV (close, open, high, low, volume)** | Snapshot | `load_snapshot_data(snapshot_id)` → per-symbol DataFrames with `date`, `open`, `high`, `low`, `close`, `volume` (and `iv_rank` if in CSV). Stored as JSON in `market_snapshot_data` | `find_csp_candidates(symbol_to_df, regime)` and, indirectly, `score_assignment_worthiness` via `candidate["key_levels"]` |
| **Technical series (EMA50, EMA200, ATR, RSI)** | Derived in code | `find_csp_candidates()` in `app/core/wheel.py` computes from the snapshot DataFrame: `ema50`, `ema200`, `atr`, `rsi` (~68–80) | Filters (uptrend, pullback, RSI) and `key_levels` passed to assignment scoring |

**Constants (no live inputs):**

- `MIN_PRICE`, `MAX_PRICE`, `TARGET_LOW`, `TARGET_HIGH` from `app/core/config/trade_rules.py` (~56–76).
- Used in `evaluate_csp_symbol()` for price gates and price-suitability score (~812–875).

---

## 3. Option Greeks and per-contract implied volatility

**No option Greeks or per-contract implied volatility are used in the heartbeat CSP path.**

- **Heartbeat call:** `find_csp_candidates(symbol_to_df, regime)` — only two arguments; no `orats_client` (`heartbeat.py` ~411–412).
- **Wheel implementation:** `find_csp_candidates(..., orats_client=None, ...)` (`wheel.py` ~16–23). When `orats_client` is `None`, the block that fetches options and calls `select_short_put()` is skipped (~147–190). Candidates are “stock-only” (no contract, delta, or IV).
- **`evaluate_csp_symbol`:** Uses a single `iv_rank` value per symbol (0–100 style). That value comes from the snapshot’s `iv_rank` column, not from any options API or Greeks calculation.
- **`get_snapshot_prices`:** Reads `iv_rank` from the DataFrame if present; there is no use of delta, gamma, vega, or per-strike IV in this or any caller in the eval path.

So the current design uses at most one aggregate IV-related field (`iv_rank`) from the snapshot. There is no options chain, no per-contract IV, and no Greeks in the evaluation or candidate-selection logic that runs in the heartbeat.

---

## 4. Evaluator logic (what uses the signals)

**`HeartbeatManager.evaluate_csp_symbol()`** (`heartbeat.py` ~746–954):

- **Gates (hard reject):**  
  - `price` None or ≤ 0 → `missing_or_invalid_price`  
  - `price` outside `[MIN_PRICE, MAX_PRICE]` → `price_out_of_range`  
  - `regime` in `("RISK_OFF", "UNKNOWN")` → `regime_not_risk_on`  
  - `volume` is not None and < 1_000_000 → `low_liquidity`  
  - `iv_rank` is not None and < 20 → `iv_too_low`
- **Scoring (0–100):**  
  - Price suitability (0–30) from `TARGET_LOW`/`TARGET_HIGH` and bounds  
  - Regime (0–30): RISK_ON 30, NEUTRAL 15, else 0  
  - Universe priority (0–20) from metadata tier/priority or default 10  
  - Freshness (0–20) from `snapshot_age_minutes`  
  - IV rank score (0–20): iv_rank ≥ 50 → 20, ≥ 30 → 10, else 0  
  - Liquidity bonus (0–10) from `volume` tiers  

**`find_csp_candidates()`** (`wheel.py` ~16–197):

- Uses only the OHLCV DataFrame and `regime`.
- Builds EMAs, ATR, RSI from `close`/`high`/`low`/`volume`.
- Filters: uptrend (close > EMA200), pullback (close near EMA50), RSI < 55.
- No Greeks, no IV, no options data in the heartbeat invocation.

**`score_assignment_worthiness()`** (`assignment_scoring.py` ~21–120):

- Uses `candidate["key_levels"]` (close, ema50, ema200, atr, rsi) and `candidate["score"]`, plus `regime`.
- No options, no IV, no Greeks.

---

## 5. Where each signal is computed or stored

| Signal | Computed / stored in | Consumed in |
|--------|----------------------|------------|
| price | Snapshot CSV/DB → `_load_snapshot_from_csv` / `load_snapshot_data`; `get_snapshot_prices` maps `close`/`price` to `price` | heartbeat `evaluate_csp_symbol`, `get_snapshot_prices` callers |
| volume | Same snapshot load path; column `volume` | `evaluate_csp_symbol` |
| iv_rank | Snapshot CSV/DB column `iv_rank`; `get_snapshot_prices` passes it through | `evaluate_csp_symbol` (gate and iv_rank_score) |
| regime | `market_regimes` table, `get_latest_regime()` | `_evaluate_cycle`, `evaluate_csp_symbol`, `find_csp_candidates`, `score_assignment_worthiness` |
| EMA50/EMA200/ATR/RSI | `find_csp_candidates()` in `wheel.py` from snapshot OHLCV | `find_csp_candidates` filters and `key_levels` → `score_assignment_worthiness` |

---

## 6. Missing vs. an options-Greeks-based strategy

Compared to a strategy that would rely on option Greeks and per-contract IV:

- **No options chain:** Options data is never fetched in the heartbeat path (`orats_client` is never passed to `find_csp_candidates`).
- **No per-strike or per-expiry IV:** Only a single `iv_rank` (or null) per symbol from the snapshot is used; there is no implied volatility by strike or expiry.
- **No Greeks:** Delta, gamma, vega, theta are not used in eligibility, scoring, or assignment.
- **No contract selection in the loop:** No DTE/delta/premium selection is performed in the evaluation cycle; the wheel’s optional `select_short_put` path is unused when called from the heartbeat.
- **iv_rank semantics:** When present, it is treated as a 0–100 style rank (e.g. low < 20 rejected, ≥ 50 favored). It is not tied to any specific option or pricing model in this codebase.

So the current implementation is **snapshot- and regime-driven**, with **one aggregate iv_rank per symbol** and **no option-level data** in the CSP evaluation path. Any move to a Greeks/IV-based strategy would require new data sources, new signals (per-strike/expiry IV, Greeks), and new or extended evaluators; none of that exists in the current signal contract.
