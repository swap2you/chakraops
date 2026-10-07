# Final Acceptance Rule

R70 local whole-application acceptance requires:

1. No BLOCKER.
2. No unresolved HIGH.
3. Cowork complete revalidation PASS or PASS_WITH_NOTES with no safety/correctness gap.
4. Codex GO or GO_WITH_NOTES with no HIGH correctness/security issue.
5. TRUE full backend suite `pytest tests/` completes green.
6. Full frontend test/type/build green.
7. Fresh clean runtime evidence.
8. Robinhood remains read-only.
9. No production deployment yet.
10. No R71.

Only then may Cursor set:

`CHAKRAOPS R70 LOCAL WHOLE-APPLICATION ACCEPTANCE COMPLETE — READY FOR PRODUCTION DEPLOYMENT PHASE`
