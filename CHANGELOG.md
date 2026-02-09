# Changelog

All notable changes to ChakraOps are recorded here. The project uses [semantic versioning](https://semver.org/) (MAJOR.MINOR.PATCH). See [chakraops/docs/BASELINE.md](chakraops/docs/BASELINE.md) for release discipline and breaking-change policy.

---

## [0.1.0] — Baseline Release

**Date:** 2026-02-09

- **Baseline established.** Phases 1–6 complete and validated; Phase 6b test hygiene applied.
- **Scope:** Universe evaluation (2-stage pipeline), Dashboard and run consumption, Phase 6 data dependency enforcement (required missing → BLOCKED), ranking and capital hints, alerts and lifecycle, decision quality and exits, tracked positions and portfolio context, REST API and frontend (Dashboard, Ranked Universe, Ticker, Tracked Positions, Decision Quality, Notifications, History, Pipeline).
- **Non-goals:** No broker integration, no inference of missing data, no automated trading, no new strategy/signal logic in baseline.
- **Validation:** Backend pytest 1235 passed, 0 failed; frontend build and tests pass. See [chakraops/docs/PHASE6_VALIDATION_REPORT.md](chakraops/docs/PHASE6_VALIDATION_REPORT.md) and [chakraops/docs/PHASE7_VALIDATION_REPORT.md](chakraops/docs/PHASE7_VALIDATION_REPORT.md).
