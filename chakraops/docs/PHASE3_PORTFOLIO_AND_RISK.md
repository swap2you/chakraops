# Phase 3: Portfolio & Risk Intelligence

This document describes Phase 3 deliverables: portfolio aggregation, risk profile, exposure metrics, risk-aware ranking, portfolio alerts, and UI.

## Overview

Phase 3 adds portfolio-level visibility and risk controls to help users avoid overexposure, concentration risk, and capital lock-up. All execution remains manual — no broker integration, no automated trades.

## Assumptions (documented in code)

- We do not know real broker balances; we rely on user-defined Accounts equity and manual tracked positions.
- Required capital for CSP = collateral = strike × 100 × contracts (existing sizing logic).
- For CC, required capital is 0 (shares already owned). Phase 3 counts CC exposure as 0.
- Sector mapping is local (company_data); unknown sectors bucketed as "Unknown" and treated conservatively.

## Files Added

### Backend

| Path | Purpose |
|------|---------|
| `app/core/portfolio/models.py` | RiskProfile, ExposureItem, PortfolioSummary, RiskFlag |
| `app/core/portfolio/store.py` | risk_profile JSON persistence (out/portfolio/risk_profile.json) |
| `app/core/portfolio/service.py` | compute_portfolio_summary, compute_exposure |
| `app/core/portfolio/risk.py` | evaluate_risk_flags, would_exceed_limits |
| `app/core/alerts/portfolio_alerts.py` | build_portfolio_alerts_for_run |
| `tests/test_portfolio.py` | Portfolio aggregation, exposure, risk profile, risk checks |

### Frontend

| Path | Purpose |
|------|---------|
| `frontend/src/types/portfolio.ts` | PortfolioSummary, ExposureItem, RiskProfile, RiskFlag |
| `frontend/src/pages/PortfolioPage.tsx` | Portfolio dashboard |
| `frontend/src/components/PortfolioSummaryCards.tsx` | Summary cards |
| `frontend/src/components/ExposureTable.tsx` | Reusable exposure table |
| `frontend/src/components/RiskProfileForm.tsx` | Risk profile editor |

## Files Modified

| Path | Change |
|------|--------|
| `app/core/market/company_data.py` | Added `get_sector(symbol)` — returns sector or "Unknown" |
| `app/core/ranking/service.py` | Risk-aware ranking: risk_context, include_blocked, risk_status, risk_reasons |
| `app/core/alerts/models.py` | Added PORTFOLIO_RISK_WARN, PORTFOLIO_RISK_BLOCK |
| `app/core/alerts/alert_engine.py` | Portfolio alerts integration, portfolio_alert_cooldown_hours (12h) |
| `app/core/alerts/slack_notifier.py` | _build_portfolio_blocks for portfolio alerts |
| `app/api/server.py` | GET /api/portfolio/summary, /exposure, /risk-profile; PUT /api/portfolio/risk-profile; dashboard include_blocked |
| `frontend/src/data/endpoints.ts` | portfolioSummary, portfolioExposure, portfolioRiskProfile, portfolioRiskProfilePut |
| `frontend/src/types/opportunities.ts` | risk_status, risk_reasons on RankedOpportunity |
| `frontend/src/components/TopOpportunities.tsx` | Risk column, Execute disabled for BLOCKED |
| `frontend/src/components/RankedTable.tsx` | Risk column, Execute disabled for BLOCKED, include_blocked=true |
| `frontend/src/App.tsx` | Route /portfolio, import PortfolioPage |
| `frontend/src/components/CommandBar.tsx` | Portfolio nav link (PieChart icon), shortcut o |
| `config/alerts.yaml` | portfolio_alert_cooldown_hours, PORTFOLIO_RISK_WARN, PORTFOLIO_RISK_BLOCK enabled |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/portfolio/summary | total_equity, capital_in_use, available_capital, utilization %, risk_flags |
| GET | /api/portfolio/exposure | group_by=symbol\|sector — exposure items with required_capital, pct_of_equity |
| GET | /api/portfolio/risk-profile | Risk profile settings |
| PUT | /api/portfolio/risk-profile | Update risk profile |
| GET | /api/dashboard/opportunities | Added include_blocked param; each opportunity has risk_status, risk_reasons |

## Risk Profile (out/portfolio/risk_profile.json)

| Field | Default | Description |
|-------|---------|-------------|
| max_capital_utilization_pct | 0.35 | Max % of equity in use |
| max_single_symbol_exposure_pct | 0.10 | Max % per symbol |
| max_single_sector_exposure_pct | 0.25 | Max % per sector |
| max_open_positions | 12 | Max open positions |
| max_positions_per_sector | 4 | Max positions per sector |
| allowlist_symbols | [] | Optional allowlist |
| denylist_symbols | [] | Optional denylist |
| preferred_strategies | [CSP, CC, STOCK] | Strategy order |
| stop_loss_cooldown_days | null | Optional cooldown after stop-loss (off by default) |

## How to Test Manually

1. **Create accounts** — Add at least one account with total_capital (e.g. $100,000) via Accounts page.

2. **Create tracked positions** — Add OPEN CSP positions via Ticker page Execute (Manual), e.g. NVDA 170P × 2.

3. **Open /portfolio** — Verify:
   - Total Equity = sum of account capital
   - Capital In Use = sum of CSP collateral (strike × 100 × contracts)
   - Available Capital = total_equity - capital_in_use
   - Utilization %
   - Exposure by Symbol and By Sector tables
   - Open Positions table (lifecycle badge, last directive)

4. **Risk Profile** — Edit thresholds (e.g. max utilization 0.35), save, verify persistence.

5. **See blocked opportunities** — With positions consuming >35% equity, open Dashboard or Universe; opportunities that would exceed limits show risk_status=BLOCKED, Execute disabled, tooltip "Why blocked".

6. **Trigger portfolio risk alert** — Exceed max utilization (e.g. add more positions or lower total_equity); run evaluation; check Slack for PORTFOLIO_RISK_BLOCK alert. Cooldown: 12h.

## Migration Notes

- **Create out/portfolio/** — The store creates it on first use. No migration script needed.
- **Default risk profile** — If risk_profile.json is missing, defaults are used (0.35, 0.10, 0.25, 12, 4).
- **Existing tests** — All 47 portfolio + lifecycle + ranking tests pass.
