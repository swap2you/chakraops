# DOMAIN_VPS_BINDING_EXTERNAL — R57

## Status

**`DOMAIN_VPS_BINDING_EXTERNAL`**

No public domain name and no VPS / cloud host credentials were supplied for this R57 scaffolding pass. ChakraOps therefore cannot claim live HTTPS binding, DNS cutover, or edge MFA (e.g. Cloudflare Access/Tunnel) against a real origin.

## What R57 *did* deliver (local / domain-ready)

- Reproducible production images under `deploy/`
- Compose stack: `api` (uvicorn), `frontend` (nginx SPA + `/api` proxy), optional `postgres`, optional `monitor` placeholder
- Env profile template: `deploy/.env.prod.example` (`APP_PUBLIC_URL`, CORS placeholders, fail-closed scheduler / non-execution flags)
- API kept off the host publish surface (proxy-only)
- Safety defaults: scheduler off, `trade_execution=false`, `manual_only=true`, no broker writes

## What remains external (operator / infra)

| Item | Why blocked |
|------|-------------|
| Register / point DNS A/AAAA or CNAME | No domain supplied |
| Attach VPS / VM / managed host | No VPS supplied |
| Terminate TLS at edge (Caddy / Cloudflare / LB) | Needs public hostname + cert path |
| Cloudflare Access / Tunnel private app pattern | Needs Cloudflare account + tunnel token |
| Firewall allowlist for SSH / tunnel only | Needs host |
| Production restore drill on remote volumes | Needs remote persistence target |

## Unblock checklist (when domain + VPS exist)

1. Provision host; install Docker Engine + Compose plugin.
2. Copy `deploy/.env.prod.example` → `.env.prod` on host; set strong secrets; never commit.
3. Set `APP_PUBLIC_URL=https://<your-domain>` and CORS to that origin.
4. Prefer Cloudflare Tunnel (or equivalent) so origin API/ports are not public; terminate TLS at edge.
5. Mount Robinhood token via `ROBINHOOD_MCP_TOKEN_PATH` (file/secret), not image layers.
6. Enable `--profile postgres` (or managed Postgres); run migrations; confirm volume persistence.
7. Smoke: `GET https://<domain>/api/healthz` → ok; confirm scheduler remains disabled; confirm no write paths.
8. Document backup/restore against remote volumes (see master `PRODUCTION_RUNBOOK.md` / backup runbooks).

## Continue program

R58–R60 may proceed on application features while this infra marker remains. Do not treat scaffolding as “production publicly reachable” until this marker is cleared with real binding evidence.
