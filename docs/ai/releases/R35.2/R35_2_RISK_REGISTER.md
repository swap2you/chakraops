# R35.2 Risk Register

| ID | Risk | Sev | Mitigation |
|----|------|-----|------------|
| R2-1 | Stop script kills an unrelated process (PID reuse / foreign process on port) | H | Require TWO signals (record/port + command identity); age guard vs record `created_at`; fail-safe refuse on ambiguity |
| R2-2 | Stop script kills Docker on :8000 | H | Never target 8000; only role ports 18800/18873 (or record overrides); command identity must match uvicorn/vite/node |
| R2-3 | Tree-kill removes too much | M | taskkill /T only on verified-owned root PID (npm→node child is intended) |
| R2-4 | Idempotency regressions (double stop, partial start) | M | Not-running PID → "already stopped"; missing record → "nothing to stop" |
| R2-5 | docker compose config leaks/creates a secret .env | H | Transient EMPTY non-secret .env, removed only if we created it; pre-existing .env untouched; no commit |
| R2-6 | Scope creep into strategy/threshold code | H | Exact authorized-path manifest; forbidden list; docs-only authorization commit first |
| R2-7 | Windows-only PS test can't run in Linux CI | L | Self-test is local evidence; CI (pytest) unaffected; documented |
| R2-8 | Behavioral change to start script relied upon by stop | M | start_chakraops.ps1 unchanged; stop reads existing record schema only |
