# R40.1 — Findings

## Probe: ORATS historical options entitlement (safe; token never printed)

| Endpoint | Result | Notes |
|----------|--------|-------|
| `/datav2/hist/dailies` | Implemented in code | Equity dailies only |
| `/datav2/hist/strikes` | HTTP 200 on probe (SPY) | Strikes hist reachable on this token |
| `/datav2/hist/options` | HTTP 403 | Explicit deny — not entitled |
| R40 Strategy Lab engine | Fixture / SIMULATION only | No production hist-options client wired |

## Verdict on R40 backtest claim
Do **not** claim ORATS historical options backtest complete.
Honest program label: **`TECHNICALLY_READY_WITH_EXTERNAL_BACKTEST_ENTITLEMENT_GAP`**.
Fixture lane remains labeled **SIMULATION**.

## Stabilization findings addressed
| Area | Severity | Disposition |
|------|----------|-------------|
| `.env` could enable legacy schedulers | BLOCKER | Fail-closed unless `CHAKRAOPS_ALLOW_ENV_SCHEDULER_OPT_IN` |
| Overlapping universe evals | HIGH | `eval_coordinator` + 409 |
| Wheel cash = total_capital | HIGH | Fixed; zero cash stays 0 |
| ORATS field_presence false negatives | MEDIUM | Side-specific live/strikes keys |
| Universe CSV duplicates | MEDIUM | Deduped to 166 unique |
| Slack status honesty | MEDIUM | CODE_READY vs CONFIGURED |
| Status claimed COMPLETE early | HIGH | Set to FINAL_ACCEPTANCE_HOLD |

## Universe
Canonical `config/universe.csv`: **166** unique symbols (A–Z sorted). Prior “167” docs were approximate/stale.
