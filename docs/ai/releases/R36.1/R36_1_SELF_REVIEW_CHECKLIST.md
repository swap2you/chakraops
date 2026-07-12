# R36.1 Self-Review Checklist

- [ ] Only authorized paths changed (git diff --name-only vs manifest).
- [ ] Gate/strategy/engine emission unchanged; decision outputs byte-identical (regression suite).
- [ ] `explanation` is additive/optional; no existing item key removed or renamed.
- [ ] Near-miss cannot bypass safety-critical gates; never mutates status.
- [ ] No fabricated measured values; None when data absent; units present.
- [ ] No raw FAIL_/WARN_ in UI-facing explanation text.
- [ ] No threshold/eligibility/ranking/sizing/allocation change.
- [ ] No scheduler/broker/universe/Slack change; manual_only=true; trade_execution=false.
- [ ] No `.env`/prompt-library/credentials committed.
- [ ] Backend + frontend gates green; new tests cover registry, contract, near-miss, API.
- [ ] Evidence captured with real command output.
