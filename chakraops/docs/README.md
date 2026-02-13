# ChakraOps documentation

**ChakraOps** is an operator-driven system for screening options candidates (cash-secured puts and covered calls) on a fixed universe. It evaluates symbols against data quality, liquidity, and market regime, and produces ELIGIBLE / HOLD / BLOCKED verdicts with reasons. It does not execute trades; the operator decides whether to place a trade.

---

## Where to start

**Start with [RUNBOOK_EXECUTION.md](./RUNBOOK_EXECUTION.md) if operating the system.** That runbook is the entry point for daily operation: quick start, backend/frontend startup, smoke tests, and verification.

---

## Documentation map

| Need | Document |
|------|----------|
| **How to operate** | [RUNBOOK_EXECUTION.md](./RUNBOOK_EXECUTION.md) — run, verify, debug, validate |
| **Data rules** | [DATA_CONTRACT.md](./DATA_CONTRACT.md) — required/optional data, staleness, BLOCKED/WARN/PASS, overrides |
| **ORATS API** | [ORATS_API_Reference.md](./ORATS_API_Reference.md), [orats_endpoint_matrix.md](./orats_endpoint_matrix.md) |
| **Keep list (cleanup)** | [phase0_keep_list.md](./phase0_keep_list.md) |

---

## Artifact retention

`artifacts/` and `out/` are generated at runtime and are not committed. Retain only what you need for debugging; e.g. keep the last ~10 runs per type in `artifacts/runs/` and trim older `artifacts/validate/` and `artifacts/phase0*` files periodically. Do not commit `artifacts/` or `out/` to git.
