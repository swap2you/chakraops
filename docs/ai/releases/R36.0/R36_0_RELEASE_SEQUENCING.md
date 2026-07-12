# R36.0 Release Sequencing Plan (Proposed)

Ordered lowest-risk-first; each sub-release is separately owner-authorized, gated, and reversible. No sub-release enables schedulers, broker writes, or unbacktested thresholds.

| Seq | Sub-release | Theme | Risk | Depends on | Threshold change? |
|-----|-------------|-------|------|-----------|-------------------|
| 1 | R36.1 | Explainability + canonical reason-code registry + near-miss on decision_engine (G5,G6,G7,G13) | Low-Med | D-1 | No |
| 2 | R36.2 | Universe V2 states (WATCH/QUARANTINE) + pass/fail history + admission/removal policy (G1-G4) | Med | D-4, R36.1 | No |
| 3 | R36.3 | Trust surface + calculation traceability UI + honest data/event status (G10) | Med | R36.1, R36.2 | No |
| 4 | R36.4 | CSP-vs-share explainable arbitration (G8) | Med-High | D-8, backtest | Weights PENDING-BACKTEST |
| 5 | R36.5 | Threshold consolidation onto strategy_profiles.yaml (G9,G12) | High | D-1,D-2, backtest parity | Only after backtest |
| 6 | R36.6 (optional) | Robinhood read-only snapshot adapter (design §35-38) | High (safety) | D-6, owner gate | No (read-only) |
| — | Ongoing | Slack contract pruning + UX redundancy cleanup (from observation) | Low | D-9 | No |

Rules:
- Any `[PENDING-BACKTEST]` value stays out of production until backtest + out-of-sample + owner sign-off.
- R36.5 (threshold consolidation) must prove behavioral parity via golden vectors before any intentional value change.
- R36.6 is optional and independently gated; absence does not block other sub-releases.
