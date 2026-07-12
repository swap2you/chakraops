# R35.2 — Operational Hardening — Scope

Base: `main` @ `7a0df58` (R35.1 closed + R35.1 post-merge Cowork UAT PASS WITH NOTES).
Branch: `release/R35.2-operational-hardening`.

## Purpose
Close two known operational gaps carried forward from R35.1 without rewriting R35.1 history:
1. `stop_chakraops.ps1` cannot stop module-form launches (`python -m uvicorn`) — AR-1 from R35.1 reviews.
2. `docker compose config` was never actually executed end-to-end (only YAML-parse validated).

## In scope
- Rewrite `scripts/stop_chakraops.ps1` to safely stop both executable-form and module-form processes, using multiple ownership signals (ownership record PID + expected port + command identity + repo/runtime identity + record age), idempotent for already-stopped/partial-start, and fail-safe when ownership is ambiguous. Must never kill unrelated Python/Node/Docker processes.
- Add a focused self-test harness for the stop logic (local; not CI-run since CI is Linux/pytest).
- Execute real `docker compose config` with safe transient non-secret variables; validate host→container mappings (18800→8000, 18873→80).
- Document the new stop behavior and a pre-UAT "stack up" checklist (Cowork Note 6) in the startup/troubleshooting runbooks.

## Out of scope (explicitly)
- No threshold/strategy/eligibility/ranking/sizing changes.
- No scheduler or recurring-job enablement.
- No Robinhood/broker integration; no order construction; no auto-trading.
- No R36 explainability work (that is R36.1).
- No Universe V2.
- No broad Ruff cleanup; no unrelated UI redesign; no deployment.
- Pre-existing data conditions (Decision Store CRITICAL, ORATS Degraded, positions reconcile, guardrails, Slack unconfigured) are NOT R35.2 defects and are left as-is.

## Cowork R35.1 UAT classification
- Scenarios 1–9, 12–16: PASS → no action.
- Scenarios 10/11 (backend-down + recovery): NOT TESTED → R36.1-relevant browser handoff; non-blocking here.
- Notes 1–5, 7: pre-existing data conditions → later releases, non-blocking.
- Note 6 (stack not running at UAT start): R35.2 non-blocking → add checklist doc.
- README gaps: real-browser UAT now done; `docker compose config` → executed for real in R35.2.
- No R35.2 blockers identified.

## Safety invariants (unchanged)
advisory-only; `manual_only=true`; `trade_execution=false`; scheduler + recurring jobs disabled; ORATS only; no broker writes; no `.env`/credential exposure; never commit the prompt library.
