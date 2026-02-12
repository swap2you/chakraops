# Provider Purge Report — THETA / yfinance / Alternate Provider References

**Generated:** Grep over repo for THETA, yfinance, ThetaTerminal, data_source=THETA, ThetaData, YFinance, and provider selection logic.  
**Rule (RUNTIME_RULES.md):** ORATS only in runtime; no Theta, no yfinance, no alternate providers in active code paths.

---

## 1. Runtime code paths (app/ — must remove or archive from active import)

### 1.1 Provider selection (ThetaTerminal → YFinance → SnapshotOnly)

| File | Line | Match |
|------|------|--------|
| app/market/live_market_adapter.py | 5 | Selects provider: ThetaTerminalHttp -> YFinance -> SnapshotOnly. |
| app/market/live_market_adapter.py | 24 | data_source: str  # e.g. "ThetaTerminal", "yfinance (stocks-only)", "SNAPSHOT ONLY" |
| app/market/live_market_adapter.py | 38 | def _select_provider(...) |
| app/market/live_market_adapter.py | 39 | """Select first healthy provider: ThetaTerminal -> YFinance -> SnapshotOnly...""" |
| app/market/live_market_adapter.py | 40 | from app.market.providers import ThetaTerminalHttpProvider, YFinanceProvider, SnapshotOnlyProvider |
| app/market/live_market_adapter.py | 41 | theta = ThetaTerminalHttpProvider() |
| app/market/live_market_adapter.py | 44 | return theta, "ThetaTerminal" |
| app/market/live_market_adapter.py | 45 | logger.info("ThetaTerminal not used: %s", detail) |
| app/market/live_market_adapter.py | 47 | yf = YFinanceProvider() |
| app/market/live_market_adapter.py | 50 | return yf, "yfinance (stocks-only)" |
| app/market/live_market_adapter.py | 52 | logger.info("YFinance not used: %s", e) |
| app/market/live_market_adapter.py | 62 | """Fetch live market data. Provider order: ThetaTerminal -> YFinance -> SnapshotOnly.""" |
| app/market/live_market_adapter.py | 65 | provider, data_source = _select_provider(out_dir) |
| app/market/live_market_adapter.py | 86 | __all__ = [..., "_select_provider"] |

| app/market/providers/__init__.py | 6 | from ... thetaterminal_http import ThetaTerminalHttpProvider |
| app/market/providers/__init__.py | 7 | from ... yfinance_provider import YFinanceProvider |
| app/market/providers/__init__.py | 12 | "ThetaTerminalHttpProvider", |
| app/market/providers/__init__.py | 13 | "YFinanceProvider", |

| app/market/providers/thetaterminal_http.py | 3 | """ThetaTerminal v3 HTTP provider (PRIMARY).""" |
| app/market/providers/thetaterminal_http.py | 5 | Base URL ... THETA_REST_URL |
| app/market/providers/thetaterminal_http.py | 24 | THETA_V3_PREFIX |
| app/market/providers/thetaterminal_http.py | 31 | THETA_BASE_URL = None |
| app/market/providers/thetaterminal_http.py | 32 | THETA_V3_PREFIX = "/v3" |
| app/market/providers/thetaterminal_http.py | 36 | class ThetaTerminalHttpProvider |
| app/market/providers/thetaterminal_http.py | 37 | """Primary provider: ThetaTerminal v3 over HTTP...""" |
| app/market/providers/thetaterminal_http.py | 45 | self.v3_url = ... THETA_V3_PREFIX |
| app/market/providers/thetaterminal_http.py | 59 | return True, "ThetaTerminal OK" |
| app/market/providers/thetaterminal_http.py | 60 | return False, f"ThetaTerminal HTTP ..." |
| app/market/providers/thetaterminal_http.py | 62 | return False, f"ThetaTerminal unreachable: ..." |
| app/market/providers/thetaterminal_http.py | 98 | logger.debug("ThetaTerminal price ..." |
| app/market/providers/thetaterminal_http.py | 129 | """ThetaTerminal can support this...""" |
| app/market/providers/thetaterminal_http.py | 133 | __all__ = ["ThetaTerminalHttpProvider", "THETA_BASE_URL"] |

| app/market/providers/yfinance_provider.py | 3 | """YFinance provider (FALLBACK).""" |
| app/market/providers/yfinance_provider.py | 15 | class YFinanceProvider |
| app/market/providers/yfinance_provider.py | 16 | """Fallback: yfinance for underlying prices only.""" |
| app/market/providers/yfinance_provider.py | 20 | import yfinance as yf |
| app/market/providers/yfinance_provider.py | 28 | "yfinance not installed" |
| app/market/providers/yfinance_provider.py | 30 | import yfinance as yf |
| app/market/providers/yfinance_provider.py | 34 | "yfinance no data" |
| app/market/providers/yfinance_provider.py | 35 | return True, "yfinance OK (stocks only)" |
| app/market/providers/yfinance_provider.py | 37 | return False, f"yfinance: {e}" |
| app/market/providers/yfinance_provider.py | 44 | import yfinance as yf |
| app/market/providers/yfinance_provider.py | 54 | logger.debug("yfinance price ..." |
| app/market/providers/yfinance_provider.py | 56 | logger.warning("yfinance fetch_underlying_prices..." |
| app/market/providers/yfinance_provider.py | 64 | __all__ = ["YFinanceProvider"] |

### 1.2 ThetaData provider (app/core/market_data)

| app/core/market_data/thetadata_provider.py | (full file) | ThetaData provider implementation; THETA_REST_URL; ThetaData Terminal; ThetaDataProvider class |

### 1.3 yfinance adapter / factory / stock snapshot provider

| app/core/market_data/yfinance_adapter.py | 3 | """YFinance adapter...""" |
| app/core/market_data/yfinance_adapter.py | 18 | from app.data.yfinance_provider import YFinanceProvider |
| app/core/market_data/yfinance_adapter.py | 23 | class YFinanceMarketDataAdapter |
| app/core/market_data/yfinance_adapter.py | 26-28 | yfinance ... ThetaDataProvider |
| app/core/market_data/yfinance_adapter.py | 33 | self.price_provider = YFinanceProvider() |
| app/core/market_data/yfinance_adapter.py | 97, 115-119, 131, 153-157, 184, 202 | yfinance / ThetaDataProvider refs |

| app/core/market_data/factory.py | 19 | """... Uses YFinance (no ThetaData dependency).""" |
| app/core/market_data/factory.py | 21 | from ... yfinance_adapter import YFinanceMarketDataAdapter |
| app/core/market_data/factory.py | 22 | provider = YFinanceMarketDataAdapter() |
| app/core/market_data/factory.py | 23 | "Using YFinanceMarketDataAdapter" |
| app/core/market_data/factory.py | 26 | "YFinance adapter not available" |
| app/core/market_data/factory.py | 28 | "Failed to initialize YFinance adapter" |
| app/core/market_data/factory.py | 31 | "Install yfinance: pip install yfinance" |

| app/data/stock_snapshot_provider.py | 3 | """Stock snapshot provider (yfinance). No Theta dependency.""" |
| app/data/stock_snapshot_provider.py | 22 | import yfinance as yf |
| app/data/stock_snapshot_provider.py | 55 | """Fetch stock snapshot from yfinance..." |
| app/data/stock_snapshot_provider.py | 67 | "yfinance_not_installed" |

| app/data/yfinance_provider.py | 3 | """yfinance price provider implementation (fallback).""" |
| app/data/yfinance_provider.py | 13 | import yfinance as yf |
| app/data/yfinance_provider.py | 20 | class YFinanceProvider |
| app/data/yfinance_provider.py | 21 | """Fetch daily OHLCV bars from yfinance..." |
| app/data/yfinance_provider.py | 24 | """Initialize yfinance provider.""" |
| app/data/yfinance_provider.py | 27-28 | "yfinance is not installed..." |
| app/data/yfinance_provider.py | 38 | "yfinance is not available" |
| app/data/yfinance_provider.py | 89 | __all__ = ["YFinanceProvider"] |

### 1.4 Config / settings (Theta env vars)

| app/core/settings.py | 30 | """ThetaData Terminal configuration.""" |
| app/core/settings.py | 97 | THETA_REST_URL, THETA_TIMEOUT, THETA_FALLBACK_ENABLED |
| app/core/settings.py | 121, 125, 128, 139, 147 | THETA_* env vars |

| app/core/config.py | 30 | """ThetaData Terminal configuration.""" |
| app/core/config.py | 77 | THETA_REST_URL, THETA_TIMEOUT, THETA_FALLBACK_ENABLED |
| app/core/config.py | 101, 105, 108 | THETA_* |

### 1.5 Callers of live_market_adapter / fetch_live_market_data

| app/ui/live_decision_dashboard.py | 47 | from app.market.live_market_adapter import LiveMarketData, fetch_live_market_data |
| app/ui/live_decision_dashboard.py | 1282 | live_data = fetch_live_market_data(symbols_for_live, out_dir=out_dir) |

| app/market/__init__.py | 5 | from app.market.live_market_adapter import LiveMarketData, fetch_live_market_data |
| app/market/__init__.py | 11 | "fetch_live_market_data" |

| app/market/drift_detector.py | 11 | from app.market.live_market_adapter import LiveMarketData, _contract_key |

### 1.6 UI dashboard (yfinance, THETA display)

| app/ui/dashboard.py | 659 | st.error(f"Realtime ({data_mode.get('source', 'THETA')}): ..." |
| app/ui/dashboard.py | 1116 | # DEV-only: Seed Snapshot from fixture (no yfinance). |
| app/ui/dashboard.py | 1820 | from app.data.yfinance_provider import YFinanceProvider |
| app/ui/dashboard.py | 1821 | price_provider = YFinanceProvider() |
| app/ui/dashboard.py | 1878 | from app.data.yfinance_provider import YFinanceProvider |
| app/ui/dashboard.py | 1879 | price_provider = YFinanceProvider() |

### 1.7 EOD snapshot / regime (yfinance for daily bars)

| app/core/journal/eod_snapshot.py | 76 | Default: use YFinanceMarketDataAdapter.get_daily if available. |
| app/core/journal/eod_snapshot.py | 86 | from app.core.market_data.yfinance_adapter import YFinanceMarketDataAdapter |
| app/core/journal/eod_snapshot.py | 87 | adapter = YFinanceMarketDataAdapter() |

### 1.8 Volatility kill switch (yfinance VIX/SPY)

| app/core/risk/volatility_kill_switch.py | 5 | Uses publicly available data from yfinance (VIX, SPY). |
| app/core/risk/volatility_kill_switch.py | 20 | import yfinance as yf |
| app/core/risk/volatility_kill_switch.py | 26 | """Get latest VIX close from yfinance (symbol ^VIX).""" |
| app/core/risk/volatility_kill_switch.py | 39 | "yfinance not installed; cannot fetch VIX" |
| app/core/risk/volatility_kill_switch.py | 69 | "yfinance not installed; cannot compute SPY range" |

### 1.9 Symbol cache (ThetaData fetch)

| app/core/symbol_cache.py | 3 | """Symbol cache management for ThetaData symbols (Phase 1B.2).""" |
| app/core/symbol_cache.py | 6 | Fetching all tradable symbols from ThetaData |
| app/core/symbol_cache.py | 26 | """Fetch all tradable symbols from ThetaData and cache them.""" |
| app/core/symbol_cache.py | 39 | If ThetaData is not available... |
| app/core/symbol_cache.py | 69-99 | from thetadata_provider import ThetaDataProvider; ThetaData... |
| app/core/symbol_cache.py | 146 | "Cached ... symbols from ThetaData" |

### 1.10 Dev seed (yfinance)

| app/core/dev_seed.py | 5 | Fixture-based path (no yfinance): ... |
| app/core/dev_seed.py | 68 | when yfinance/live data is unavailable |
| app/core/dev_seed.py | 120 | """Fetch last close and volume for symbols via yfinance..." |
| app/core/dev_seed.py | 130 | not used by yfinance |
| app/core/dev_seed.py | 139 | If yfinance is unavailable |
| app/core/dev_seed.py | 142 | from app.data.yfinance_provider import YFinanceProvider |
| app/core/dev_seed.py | 145-146 | "yfinance is required for Seed Snapshot..." |
| app/core/dev_seed.py | 157 | provider = YFinanceProvider() |

### 1.11 DB / universe import (yfinance symbol mapping)

| app/db/universe_import.py | 38 | def canonical_to_provider_symbol(symbol: str, provider: str = "yfinance") |
| app/db/universe_import.py | 39 | """... (e.g. BRK.B -> BRK-B for yfinance).""" |
| app/db/universe_import.py | 44 | if provider == "yfinance": |

### 1.12 Other app references (comments / docstrings)

| app/core/options/chain_provider.py | 11 | Provider-agnostic interface (ORATS, ThetaData, etc.) |
| app/market/market_hours.py | 61 | """UI mode string: LIVE (ThetaTerminal) or LIVE (yfinance, stocks-only) or SNAPSHOT ONLY (...).""" |
| app/core/persistence.py | 283 | # Create symbol_cache table (Phase 1B.2) - for ThetaData symbol search |
| app/data/polygon_provider.py | 6 | DEPRECATED: This provider is deprecated in favor of ThetaDataProvider. |

---

## 2. Tests (active path — tests/ excluding _archived_theta and legacy)

| tests/test_drift_detector.py | 23 | from app.market.live_market_adapter import LiveMarketData |
| tests/test_volatility_kill_switch.py | 22 | """When yfinance returns VIX data...""" |
| tests/test_volatility_kill_switch.py | 34 | """When yfinance returns empty...""" |
| tests/test_volatility_kill_switch.py | 44 | """When yf is None (yfinance not installed)...""" |
| tests/test_universe_import.py | 23-24, 28 | canonical_to_provider_symbol(..., "yfinance") |

### 2.2 Archived / legacy (excluded from pytest; not imported by runtime)

| tests/_archived_theta/test_provider_selection.py | (multiple) | ThetaTerminal, yfinance, _select_provider |
| tests/_archived_theta/test_thetadata_provider.py | (multiple) | ThetaDataProvider, ThetaTerminal v3 |
| tests/_archived_theta/README.md | (multiple) | ThetaTerminal, ThetaData |
| tests/legacy/__init__.py | 1 | ThetaData |

---

## 3. Tools and scripts (not app runtime, but present)

| tools/thetadata_probe.py | 195 | "[THETA] Start ThetaTerminal v3 on port 25503..." |
| tools/thetadata_capabilities.py | 411 | "[THETA] Start ThetaTerminal v3 on port 25503..." |
| tools/seed_snapshot_from_eod.py | 2 | "... from fixture or last close (yfinance). DEV-only" |
| tools/seed_snapshot_from_eod.py | 17 | "Seed market_snapshot.csv (fixture or yfinance, DEV)" |
| tools/seed_snapshot_from_eod.py | 21 | "(no yfinance)" |
| tools/seed_snapshot_from_eod.py | 27 | "Symbols to fetch (yfinance only); ..." |

---

## 4. Documentation only (.md — no code change required for purge)

References in docs/ (CLEANUP_REPORT, TEST_AUDIT, README, DOCS_CLEANUP_REPORT, legacy/README, dev_workflow, etc.) are historical or policy; list omitted for brevity. See grep of `*.md` for full list.

---

## Summary

- **Runtime provider selection:** `app/market/live_market_adapter.py` and `app/market/providers/` (ThetaTerminalHttpProvider, YFinanceProvider) are the main active path; `fetch_live_market_data` is used by `app/ui/live_decision_dashboard.py` and exported from `app/market/__init__.py`.
- **yfinance in app:** Used by stock_snapshot_provider, yfinance_provider, yfinance_adapter, factory, dev_seed, volatility_kill_switch, eod_snapshot, dashboard (YFinanceProvider), universe_import (symbol mapping).
- **ThetaData in app:** thetadata_provider.py, symbol_cache.py, config/settings THETA_* env, persistence comment, polygon_provider deprecation text.
- **ThetaTerminal in app:** thetaterminal_http.py, live_market_adapter (_select_provider), market_hours docstring, dashboard display ('THETA').
- **Archived tests:** tests/_archived_theta/* and tests/legacy/* contain Theta/yfinance references but are excluded from pytest and not imported by app runtime.
