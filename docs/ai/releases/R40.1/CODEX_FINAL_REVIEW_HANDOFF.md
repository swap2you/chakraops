# Codex — ChakraOps Final Independent Adversarial Review After R40.1

Review current synchronized `main` read-only **after** the R40.1 stabilization commit is on `origin/main`.

Confirm `git rev-parse HEAD` == `origin/main` and record that SHA in your report (baseline before R40.1 was `99eb213`).

Do not rely on Cursor's verdict.

Attempt to falsify readiness.

Local Cursor evidence (optional, non-authoritative): `out/verification/R40.1/` (gitignored).

Mandatory checks:

1. Scheduler defaults:
   - master false
   - legacy false
   - no automatic eval on startup
   - environment precedence cannot silently override safety defaults

2. Evaluation concurrency:
   - all full-universe entry paths coordinated
   - simultaneous eval rejected
   - one canonical persistence path
   - no duplicate ORATS full-universe run

3. Portfolio financial correctness:
   - total capital != cash
   - zero cash remains zero
   - account-specific balance isolation
   - CSP cannot size against untrusted/missing collateral

4. ORATS:
   - endpoint-aware diagnostics
   - provider quote time vs request/evaluation time
   - secrets redacted
   - historical/backtest entitlement claim supported by evidence

5. Universe:
   - no duplicate canonical CSV rows
   - effective count correctly documented

6. R38 Wheel/Share:
   - manual only
   - no safety bypass
   - sizing/concentration
   - Stay in Cash

7. R39 Slack:
   - renderer does not decide
   - configuration status honest

8. R40:
   - historical/backtest claims match implementation
   - no evidence-free threshold retune
   - no look-ahead
   - SIMULATION labels

9. Final status:
   - repository does not claim independent acceptance before it occurred

10. Full gates/evidence:
    - test results
    - build
    - runtime
    - secrets
    - main == origin/main

Return:
- BLOCKER
- HIGH
- MEDIUM
- LOW
- FALSE POSITIVE
- exact evidence
- reproduction
- remediation
- GO / NO-GO

End:

`CHAKRAOPS R40.1 CODEX FINAL ADVERSARIAL REVIEW COMPLETE`
