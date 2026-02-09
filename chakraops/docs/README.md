# ChakraOps documentation

**ChakraOps** is an operator-driven system for screening options candidates (cash-secured puts and covered calls) on a fixed universe. It evaluates symbols against data quality, liquidity, and market regime, and produces ELIGIBLE / HOLD / BLOCKED verdicts with reasons. It does not execute trades; the operator decides whether to place a trade.

---

## Where to start

**Start with [RUNBOOK.md](./RUNBOOK.md) if operating the system.** The runbook is the single entry point for daily operation: quick start, daily workflow, smoke tests, debugging playbook, validation commands, and what not to do. You can operate the system using only the runbook and the links it provides.

---

## Documentation map

| Need | Document |
|------|----------|
| **How to operate** | [RUNBOOK.md](./RUNBOOK.md) — run, verify, debug, validate |
| **How the system works** | [ARCHITECTURE.md](./ARCHITECTURE.md) — evaluation pipeline, strategy model, risk & gating, decision lifecycle |
| **Data rules** | [DATA_CONTRACT.md](./DATA_CONTRACT.md) — required/optional data, staleness, BLOCKED/WARN/PASS, overrides |
| **Historical records** | [history/](./history/) — phase summaries, validation reports, preconditions (not required for operation) |

Other references (scheduling, alerts, deployment, baseline, etc.) are linked from the runbook under **Further Reading**.
