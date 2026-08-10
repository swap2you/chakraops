# ORATS Backtest Entitlement (R40.1)

## Summary
ChakraOps R40 Strategy Lab is **technically ready** as a fixture/SIMULATION research lane.
It is **not** entitled for full ORATS historical options backtests on the current API plan.

Honest status label:

`TECHNICALLY_READY_WITH_EXTERNAL_BACKTEST_ENTITLEMENT_GAP`

## Evidence (safe probe; token never logged)
| Path | Observed |
|------|----------|
| `GET /datav2/hist/strikes` | 200 (strikes history reachable) |
| `GET /datav2/hist/options` | **403** — User is not authorized (explicit deny) |
| Code | R40 walk-forward uses fixtures / synthetic trades only; labeled **SIMULATION** |

## Entitlement needed
ORATS Data API entitlement for **historical options** (`/hist/options` or equivalent full options history product) covering multi-year option chains suitable for CSP/wheel research.

Until entitled **and** a production hist-options client is implemented and validated:
- Do not claim live ORATS hist backtest complete
- Keep SIMULATION labels on Strategy Lab outputs
- Do not retune production thresholds from fixture runs

## Operator action
1. Confirm ORATS plan includes historical options (not only live + hist dailies/strikes).
2. After entitlement, add a redacted smoke proof under `out/verification/` (no tokens).
3. Only then consider upgrading the honesty string past the entitlement gap.
