# R40.1 — Acceptance

## Status
**FINAL_ACCEPTANCE_HOLD**

Not COMPLETE. Awaiting independent Codex adversarial review + Cowork UAT on synchronized `main` after R40.1 remediation.

## Program honesty (R40 backtest)
`TECHNICALLY_READY_WITH_EXTERNAL_BACKTEST_ENTITLEMENT_GAP`

- Strategy Lab / R40 lane = **SIMULATION** (fixture-driven)
- `/hist/options` not entitled (403 on safe probe)
- Do not fake ORATS hist options as complete

## Safety invariants (must hold)
- Manual only · no broker writes
- Master scheduler default false
- Legacy schedulers default false
- Fail-closed even if `.env` has LEGACY=true without allow flag
- Start script sets both scheduler env keys false
- Concurrent full-universe eval → `already_running` / HTTP 409
- Cash never coerced from total_capital

## Cursor technical gates (pre-independent review)
- Focused r400/r401: PASS
- Backend full pytest: PASS (542 passed, 1 skipped)
- Frontend vitest: PASS (349 passed, 18 skipped)
- Frontend build: PASS
- Runtime: master/legacy schedulers off; manual_only; broker NO_GO
- Local evidence: `out/verification/R40.1/` (gitignored)

## Independent reviews (required next)
- Codex: `CODEX_FINAL_REVIEW_HANDOFF.md`
- Cowork: `COWORK_FINAL_UAT_HANDOFF.md`
