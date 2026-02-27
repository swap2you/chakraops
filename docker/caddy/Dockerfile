# R24.9: Caddy with our Caddyfile.template and entrypoint (env-based basic auth).
# Build from repo root: docker build -f docker/caddy/Dockerfile .
FROM caddy:2-alpine
COPY docker/caddy/Caddyfile.template /etc/caddy/Caddyfile.template
COPY docker/caddy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
