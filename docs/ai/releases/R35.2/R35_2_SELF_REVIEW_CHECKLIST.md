# R35.2 Self-Review Checklist

- [ ] Only authorized paths changed (git diff --name-only vs manifest).
- [ ] No strategy/threshold/eligibility/ranking/sizing edits.
- [ ] `docker-compose.yml` unedited; compose config executed only.
- [ ] No `.env` / prompt library / credentials committed.
- [ ] Stop script requires >=2 ownership signals before any kill.
- [ ] Stop script never targets port 8000; Docker unaffected.
- [ ] Stop script idempotent + fail-safe on ambiguity.
- [ ] PID-reuse guarded via record `created_at` vs process StartTime.
- [ ] Backend/frontend regression gates green.
- [ ] Secret scan clean.
- [ ] Scheduler/manual-only/no-broker assertions hold.
- [ ] Evidence captured with real commands + exit codes.
