# Final Unresolved Issues — R31–R35

| ID | Issue | Disposition |
|----|-------|-------------|
| L-3 | Stale roadmap trackers | Noted; refresh deferred post-merge |
| L-4 | KNOWN_ISSUES header stale | Noted |
| L-5 | Legacy release tree frozen at R27.6 | Accepted; program docs canonical |
| L-9 | Verification path drift in old checklist | R35 evidence uses `out/verification/R35.0/` |
| R35-ACCEPT | `$StaleRoot` undefined / wildcard stale check | **CLOSED** — `chakraops_common.ps1` + start/stop remediation |
| R35-ACCEPT | Stale r350 evidence (56 vs current) | **CLOSED** — harness regenerated logs |
| R35-ACCEPT | Missing executable acceptance contract | **CLOSED** — manifest + `validate_r31_r35_release.ps1` |
| R35-ACCEPT | Windows live operational validation | **CLOSED** — smoke PASS 2026-06-23 |
| Cowork browser UAT | Browser checks on Windows UI | **PENDING** — sole remaining release gate |
| Windows orphan :8000 | Start may warn if orphan listener lacks repo path in cmdline | Non-blocking; use stop script + port cleanup |

Technical R35 blockers closed. Program acceptance pending **Cowork browser-only UAT**. No final PR. Schedules disabled.
