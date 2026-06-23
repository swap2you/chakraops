# Final PR Description — R31–R35 Program

## Title

R31–R35: program baseline, data reliability, canonical engine, live cutover, and operational readiness

## Summary

- **R31:** Repository and product baseline audit
- **R32:** ORATS secret remediation (C-1), data freshness, provider health, weekly universe
- **R33:** Canonical decision engine, profiles, risk gates
- **R34:** Live cutover (H-5 closed), transaction-safe refresh, OS-native locks, ORATS redaction, sector enforcement
- **R35:** Unified job registry and scheduler (disabled by default), atomic cross-process consistency, Windows backup PowerShell tools, retention safeguards, operations API/UI, runbooks, executable release acceptance harness

## Review and validation status

- Codex/Claude technical: **approved**
- Cowork static audit: **passed**
- Executable release acceptance harness: **PASS** (2026-06-23, commit `6804490`)
- Windows operational smoke: **PASS**
- Cowork browser UAT: **PASS WITH NOTES** (2026-06-23)
- Recurring schedules: **disabled** (unchanged by this PR)
- Deployment: **not performed**
- Merge / tag / schedule enablement: **not part of this PR**

## Test plan

- [x] Backend: `cd chakraops && python -m pytest tests -q --tb=short` — **1300 passed, 4 skipped**
- [x] R35 targeted: `cd chakraops && python -m pytest tests -k r350 -q --tb=short` — **76 passed, 1 skipped**
- [x] Frontend: `cd frontend && npm run test -- --run` — **335 passed, 18 skipped**
- [x] Frontend build: `cd frontend && npm run build` — **PASS**
- [x] Codex/Claude technical review
- [x] Cowork static audit
- [x] Windows operational smoke (`scripts/run_r31_r35_live_smoke.ps1`)
- [x] Cowork browser UAT (scheduler disabled, no broker controls, canonical recommendations, fail-closed diagnostics)
- [ ] Operator merge approval (separate decision)
- [ ] Operator schedule enablement (separate decision, post-merge)

## Safety

- **Manual trading only.** No broker integration or order execution.
- **ORATS** is the sole active market-data provider. No silent fallback.
- **Stay in Cash** remains a valid outcome.
- **Schedules disabled by default.** This PR does not enable recurring jobs.
- **Current data health** includes ORATS Degraded/WARN and Decision Store CRITICAL; the product **fails closed** correctly. Data health is not claimed green.
- **No deployment** was performed as part of program closure.

## Cowork non-blocking notes (accepted)

1. ORATS Degraded/WARN and Decision Store CRITICAL are current data-health states; fail-closed behavior verified.
2. Some Cowork screenshots were blank (capture limitation); DOM, API, console, and network validation passed.
