# R37 — Robinhood Read-Only Portfolio Synchronization — Scope

## Purpose
Feasibility gate for official/supported Robinhood **read-only** portfolio sync into ChakraOps trusted snapshots. If no safe official path exists, document **NO-GO** and continue R38 on the manual portfolio path.

## Baseline
- After R36.3 VALIDATED on `main`
- Safety invariants: `manual_only=true`, `trade_execution=false`, scheduler `master_enabled=false`
- No threshold retune; no new strategies; no broker write endpoints

## Feasibility gate (R37-F1)

| Source | Finding |
|---|---|
| Official https://docs.robinhood.com/ | **Crypto Trading API only** — not equity/options Wheel portfolio |
| Official public brokerage API (stocks/options) | **None** |
| Unofficial private API / robin-stocks / browser login | **FORBIDDEN** (ToS risk; credential scraping ban) |
| Plaid / other aggregators | Different vendor; requires owner policy — **not** “Robinhood official”; out of scope |

**Verdict: NO-GO** (R37-N1). Preserve and harden the **manual portfolio** trusted snapshot path.

## In scope (delivered)
- Documented NO-GO decision and acceptance mapping
- Hard write denylist + empty/disabled read allowlist for Robinhood
- `GET /api/ui/broker/status` read-only NO-GO JSON (no credentials)
- Portfolio UI provenance: “Manual portfolio snapshot” / user-entered, not broker-synced
- Offline tests proving denylist + status + no unofficial RH client modules under `app/`
- Acceptance manifest with `NO_GO_CONTINUE_R38`

## Out of scope / explicit bans
- Unofficial Robinhood clients or `api.robinhood.com` app clients
- Credential storage / scraping / browser-login automation
- Scheduler enablement
- Broker write / order route / cancel / exercise / assign / rebalance
- Strategy threshold loosening
- Inventing Robinhood sync UI
- Plaid as a substitute labeled “Robinhood official”

## Safety invariants preserved
- Advisory / manual execution only
- `trade_execution=false`
- Manual portfolio remains the trusted snapshot for R38 sizing
