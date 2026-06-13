# CLAUDE.md — ChakraOps Quick Reference

Read `AGENTS.md` first. This file is a thin Claude-specific supplement.

## Paths

- Repo root: `C:\Development\Workspace\ChakraOps-dev\chakraops`
- Backend: `chakraops/`
- Frontend: `frontend/`
- Master docs: `docs/master/`
- Release ledger: `chakraops/docs/releases/`
- Verification evidence: `out/verification/<Release>/notes.md`

## Commands

```bash
# Backend tests
cd chakraops && python -m pytest tests -q --tb=short

# Frontend tests
cd frontend && npm run test -- --run

# Frontend build
cd frontend && npm run build
```

## Stop Conditions

- Ambiguous scope
- Failed gate
- Conflict with `AGENTS.md`
- Operator denial
- Cursor actively editing the same release
