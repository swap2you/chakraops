# R57 Acceptance — Secure Production Deployment Scaffolding

## Status

`R57_SCAFFOLDING_COMPLETE` — local production-mode Compose/Docker scaffolding delivered.  
**Public domain / VPS binding:** `DOMAIN_VPS_BINDING_EXTERNAL` (no domain or VPS supplied).

## IDs

| ID | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| R57-D1 | `deploy/docker-compose.prod.yml` with api, frontend, optional postgres, optional monitor placeholder | **PASS** | `deploy/docker-compose.prod.yml` |
| R57-D2 | Env template via `.env.prod.example`; secrets not committed | **PASS** | `deploy/.env.prod.example`; `.gitignore` allows example only |
| R57-D3 | `Dockerfile.api` + multi-stage `Dockerfile.frontend` | **PASS** | `deploy/Dockerfile.api`, `deploy/Dockerfile.frontend` |
| R57-D4 | nginx SPA + `/api` proxy; API not published on host | **PASS** | `deploy/nginx.conf`; compose `expose` only for api |
| R57-S1 | Scheduler disabled by default; `trade_execution=false`; `manual_only=true` | **PASS** | env example + compose environment overrides; `tests/test_r57_deploy_safety.py` |
| R57-S2 | No broker write enable flags / no secrets hardcoded in deploy assets | **PASS** | `tests/test_r57_deploy_safety.py` |
| R57-H1 | Optional local smoke: compose up + healthz | **PASS** | `scripts/smoke_prod_compose.ps1` |
| R57-X1 | Domain/VPS HTTPS binding | **DOMAIN_VPS_BINDING_EXTERNAL** | `docs/ai/releases/R57/DOMAIN_VPS_BINDING_EXTERNAL.md` |

## Safety invariants (must hold)

- `CHAKRAOPS_SCHEDULER_ENABLED=false`
- `trade_execution=false`
- `manual_only=true`
- Never enable broker writes in Compose, Dockerfiles, or env examples
- Prefer `ROBINHOOD_MCP_TOKEN_PATH` over baking tokens into images

## Tests

```text
cd chakraops
pytest tests/test_r57_deploy_safety.py -q
```

Optional (requires Docker):

```text
.\scripts\smoke_prod_compose.ps1
```

## Do not claim

- Live domain TLS / Cloudflare Access / VPS attach (external)
- R58+ features
- Scheduler or trade execution enabled in any environment
- Production OAuth login completed (still token-path / UNAUTHENTICATED until operator supplies secret)
