# Final Gate Summary — R31–R35

| Milestone | Backend | Frontend tests | Build |
|-----------|---------|----------------|-------|
| R31.0 | 1018/2 skip | 308/18 skip | PASS |
| R32.0 | (see R32 evidence) | PASS | PASS |
| R33.0 | (see R33 evidence) | PASS | PASS |
| R34.0 | 1248/3 skip | 334/18 skip | PASS |
| R35.0 | **1282/1 skip** | **335/18 skip** | **PASS** |

R35 additional (final remediation): 56 R35-targeted tests; Windows spawn multiprocess consistency for occurrences, incidents, backup writer locks.

Evidence: `out/verification/R35.0/{backend,frontend,build}.log`, `multiprocess_consistency.md`.
