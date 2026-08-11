# Owner Action State — R61–R70

Domain `chakraops.cloud` purchased (IONOS). Prefer Cloudflare DNS + Access + Tunnel. Do not touch `dauji.info`.

| Action | State | Notes |
|--------|-------|-------|
| VPS provision (IONOS Ubuntu 24.04 ~6vCPU/8GB/200GB+) | READY_FOR_OWNER | Required for remote production |
| Cloudflare zone for chakraops.cloud | READY_FOR_OWNER | Full DNS setup |
| Disable IONOS DNSSEC before NS change | READY_FOR_OWNER | If DNSSEC/DS active |
| Set Cloudflare nameservers at IONOS | READY_FOR_OWNER | Exactly two CF NS from Cloudflare dashboard — do not invent; do not Reset domain |
| Cloudflare zone Active + DNSSEC via CF | READY_FOR_OWNER | After NS propagation |
| Cloudflare Access (owner MFA / OTP) | READY_FOR_OWNER | Deny-by-default |
| Cloudflare Tunnel `chakraops-prod` token on VPS | READY_FOR_OWNER | Token file only `/opt/chakraops/secrets/cloudflare_tunnel_token` mode 0600; never chat/Git |
| Robinhood production MCP OAuth | READY_FOR_OWNER | Cursor MCP ≠ production; token at `ROBINHOOD_MCP_TOKEN_PATH` |
| Slack webhook on VPS | READY_FOR_OWNER | If not already configured |
| Remote deploy + Codex/Cowork UAT | BLOCKED_ON_ABOVE | Required for CHAKRAOPS PRODUCTION GOLIVE COMPLETE |

Cursor finished independent code/deploy scaffolding on main. Remote live bind awaits this card.
