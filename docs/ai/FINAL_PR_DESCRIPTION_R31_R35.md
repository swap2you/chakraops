# Final PR Description — R31–R35 Program

## Title

R31–R35: program baseline, data reliability, canonical engine, live cutover, and operational readiness

## Summary

- **R31:** Repository and product baseline audit
- **R32:** ORATS secret remediation (C-1), data freshness, provider health, weekly universe
- **R33:** Canonical decision engine, profiles, risk gates
- **R34:** Live cutover (H-5 closed), transaction-safe refresh, OS-native locks, ORATS redaction, sector enforcement
- **R35:** Unified job registry and scheduler (disabled by default), atomic cross-process occurrence/incident/backup consistency, backup/restore, operations API/UI, Windows runbooks, final handoff

## Test plan

- [ ] Backend: `cd chakraops && python -m pytest tests -q --tb=short`
- [ ] Frontend: `cd frontend && npm run test -- --run && npm run build`
- [ ] Codex re-review after R35 atomic consistency remediation
- [ ] Cowork operational UAT (startup, ops panel, manual jobs, no auto-trading)
- [ ] Operator confirms scheduler remains disabled until explicitly enabled post-UAT

## Safety

Manual trading only. No broker integration. ORATS sole provider. Schedules disabled by default.
