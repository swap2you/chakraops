# AI Program Library Validation Checklist

Use keyword: `VALIDATE PROGRAM LIBRARY`

The validating tool must remain read-only and verify:

1. Required master files exist.
2. R31.0 through R35.0 each contain all eight required files.
3. Every release has one explicit risk level.
4. Every release names an exact branch.
5. Every release defines allowed and forbidden paths.
6. Every release lists the exact AGENTS.md baseline gates:
   - `cd chakraops && python -m pytest tests -q --tb=short`
   - `cd frontend && npm run test -- --run`
   - `cd frontend && npm run build`
7. Every release defines local evidence under `out/verification/<Release>/`.
8. No release permits automatic trading or broker order routing.
9. ORATS live checks are read-only and redact secrets.
10. Read-only reviewers are never instructed to edit status/log files.
11. Dependencies follow R31 → R32 → R33 → R34 → R35.
12. R32–R35 packets state that R31 findings may refine exact tasks without expanding locked non-goals.
13. PR, rollback, and stop-point sections exist.
14. Program status and per-release status are consistent.
15. No packet authorizes silent fallback data.

Return:
- APPROVED
- APPROVED WITH NON-BLOCKING NOTES
- BLOCKED
