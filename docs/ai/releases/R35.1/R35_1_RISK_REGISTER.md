# R35.1 — Risk Register

**Release ID:** R35.1 · **Branch:** `release/R35.1-dedicated-ports-stabilization` · **Base:** `2c1393f`

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R1 | Losing the uncommitted port work during branch recovery | Low | High | Used `git switch -c` (no stash/reset/clean); verified all 28 modified + 5 untracked files survived |
| R2 | `frontend/.env.development` accidentally committed | Medium | High | Explicitly forbidden; Phase 2 restores `.gitignore` ignore rule; secret scan confirmed no credentials |
| R3 | `.gitignore` currently un-ignores `.env.development` (`!frontend/.env.development`) | Present | High | Phase 2 must revert to keep the file ignored |
| R4 | PowerShell ignores `CHAKRAOPS_*_PORT` overrides → divergence from Python/Vite | Present | Medium | Phase 2 remediation item A (env override + fail-fast) |
| R5 | Unrelated prompt library committed into R35.1 | Low | Medium | Added to `.git/info/exclude`; forbidden in manifest |
| R6 | Scope creep into R36 strategy/Universe work | Medium | High | Out-of-scope list; forbidden paths in manifest |
| R7 | Scheduler/recurring jobs accidentally enabled | Low | High | Assertions: scheduler disabled, recurring jobs disabled |
| R8 | Broker/order capability introduced | Low | Critical | Assertions: `manual_only=true`, `trade_execution=false`, no broker-write |
| R9 | Secret exposure in logs/docs | Low | High | Secret-redaction assertion; no `.env` committed; redacted scans only |
| R10 | Docker container port confusion (8000 is intentional inside container) | Medium | Low | Classified as intentional container port in design |
| R11 | CRLF→LF normalization noise inflates diff | Present | Low | Cosmetic; validate real content diff during Phase 3 |
| R12 | App fails to start when `.env.development` absent | Low | Medium | Acceptance criterion: Vite defaults apply when file missing |
