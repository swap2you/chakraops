# R37 — Robinhood Read-Only — NO-GO Decision

**Date:** 2026-08-10  
**Verdict:** **NO-GO** — continue R38 on manual portfolio trusted snapshot.

## Official sources consulted (no scraping)

1. **Robinhood developer docs** — https://docs.robinhood.com/  
   - Documents the **Crypto Trading API** only.  
   - Does **not** provide an official public stocks/options brokerage portfolio API suitable for Wheel cash/BP/positions/collateral sync.

2. **Master program requirements** — `docs/ai/MASTER_PROGRAM_R36_3_R40_REQUIREMENTS.md` §R37  
   - Feasibility must use official/supported sources only.  
   - Credential scraping, browser-login automation as production integration, and any write path are explicit no-gos.  
   - If no safe path: documented **NO-GO**; preserve manual portfolio; continue R38.

3. **Program safety baseline** — `AGENTS.md` / `MASTER_CONTROL.md`  
   - No broker order routing; brokerage integration when approved later is hard read-only with write denylist.  
   - Robinhood was previously “accounts enum label only” with **no** integration.

## Denied approaches (must not be implemented)

| Approach | Why denied |
|---|---|
| Unofficial Robinhood private/web API | ToS risk; unsupported; credential/session fragility |
| `robin-stocks` or similar community clients | Unofficial; same ToS/credential risks |
| Browser login / session cookie automation | Credential scraping ban; production-unsafe |
| Storing RH username/password/MFA secrets | Forbidden credential handling |
| Any order place/buy/sell/cancel/exercise/assign/route | Hard write denylist; `trade_execution=false` |
| Labeling Plaid (or other aggregators) as “Robinhood official” | Different vendor; owner policy/credentials out of R37 scope |

## Why manual portfolio continues

- ChakraOps already stores user-entered cash, buying power, and holdings as the trusted snapshot used for CC eligibility and (via R38) portfolio-aware sizing.
- Without an official equity/options read API, inventing sync would either lie about freshness or violate program bans.
- R37 therefore **closes as NO-GO**, hardens the deny/allow policy modules, labels UI provenance clearly, and unblocks **R38** (Wheel & Share Decision Engine V2) on the existing manual trusted snapshot.

## Safety hardening shipped with this NO-GO

- `app/core/broker/read_only_policy.py`: empty `READ_ALLOWLIST` for RH; hard `WRITE_DENYLIST`; `robinhood_integration_status() -> NO_GO`
- `GET /api/ui/broker/status`: read-only status JSON; no credentials
- Portfolio page: visible “Manual portfolio snapshot” / not broker-synced provenance
- Tests: denylist verbs, NO-GO status, no `robin_stocks` / `api.robinhood.com` client modules under `app/`
