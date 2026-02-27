#!/bin/sh
# R24.9: Substitute BASIC_AUTH_USER, BASIC_AUTH_HASH, and optional DOMAIN from env.
set -e
: "${BASIC_AUTH_USER?BASIC_AUTH_USER not set}"
: "${BASIC_AUTH_HASH?BASIC_AUTH_HASH not set}"
SITE="${DOMAIN:-:80}"
export SITE
sed -e "s/__BASIC_AUTH_USER__/${BASIC_AUTH_USER}/g" \
    -e "s/__BASIC_AUTH_HASH__/${BASIC_AUTH_HASH}/g" \
    -e "s/__SITE__/${SITE}/g" \
    /etc/caddy/Caddyfile.template > /etc/caddy/Caddyfile
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
