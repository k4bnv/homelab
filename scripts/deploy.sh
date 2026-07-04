#!/usr/bin/env bash
set -euo pipefail

HOMELAB_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HOMELAB_ROOT"

echo "==> Creating docker network (if missing)"
docker network create frontend 2>/dev/null || true

deploy() {
  local service="$1"
  echo "==> Deploying ${service}"
  cd "${HOMELAB_ROOT}/${service}"
  docker compose up -d
}

if [[ ! -f vaultwarden/.env ]]; then
  echo "==> Creating vaultwarden/.env from example"
  cp vaultwarden/.env.example vaultwarden/.env
  echo "    Edit vaultwarden/.env before production use (DOMAIN, ADMIN_TOKEN)"
fi

deploy homepage
deploy uptime-kuma
deploy vaultwarden

echo ""
echo "Done! Open:"
echo "  Homepage:    http://192.168.178.194:3000"
echo "  Uptime Kuma: http://192.168.178.194:3001"
echo "  Vaultwarden: http://192.168.178.194:8080"
