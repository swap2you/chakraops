# STATUS — R35.0

## Current status
**RELEASE ACCEPTANCE FACTORY PASS** (automated + Windows operational smoke)

Cowork browser-only UAT: **PENDING** (sole remaining gate before final PR)

## Key commits
| Role | SHA | Message |
|------|-----|---------|
| Starting HEAD (program) | `26bd27e` | Windows tooling docs |
| Acceptance factory auth | `40e7528` | Authorize release acceptance factory + retention waiver |
| Implementation base | `9d5fe66` | Finalize executable release acceptance and Windows operations |
| Startup/shutdown auth | `307d1f1` | Authorize stale-path remediation |
| Final HEAD | `9b7563c` | Startup script test aligned to common.ps1 |

## Gates (parsed from `out/verification/R35.0/*.log` — 2026-06-23 harness run)
| Gate | Result |
|------|--------|
| Backend full | **1300 passed, 4 skipped** |
| R35 targeted (`-k r350`) | **76 passed, 1 skipped** |
| Frontend tests | **335 passed, 18 skipped** |
| Frontend build | **PASS** |
| PowerShell integrity | **PASS** |
| Authorization integrity | **PASS** |
| Windows live smoke | **PASS** |
| Security scan | **PASS** |
| Internal adversarial reviews (A/B/C) | **PASS** |
| Cowork browser UAT | **PENDING** |

## Schedules
Recurring schedules and job env defaults remain **disabled**. No final PR. No deployment.

## Evidence
`out/verification/R35.0/{backend,r350_suite,frontend,build,windows_live_smoke,powershell_validation,authorization_validation,security_scan,release_acceptance}.{log,json,md}` and `self_review/`.
