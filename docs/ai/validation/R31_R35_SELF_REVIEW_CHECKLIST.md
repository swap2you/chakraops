# R31–R35 Self-Review Checklist

## Review A — Governance adversary

- [ ] All changed paths since `40e7528` in manifest
- [ ] No retroactive authorization
- [ ] Waiver for `50919b4` retention job recorded
- [ ] Evidence timestamps after implementation commit
- [ ] No claim of Cowork browser UAT pass

## Review B — Windows operations adversary

- [ ] `chakraops_common.ps1` defines RepoRoot, StaleRoot, Backend
- [ ] No undefined `$StaleRoot` / `$Backend` in backup scripts
- [ ] Stale checkout rejected with explicit path compare (not wildcard on undefined)
- [ ] Backup create/list/verify/restore/cleanup dry-run succeed
- [ ] Destructive cleanup requires token

## Review C — Release-safety adversary

- [ ] Scheduler and jobs disabled by default
- [ ] No broker/order openapi paths
- [ ] `.env` not in backups
- [ ] Live state unchanged by smoke
- [ ] Documentation counts match parsed logs

Reports: `out/verification/R35.0/self_review/`
