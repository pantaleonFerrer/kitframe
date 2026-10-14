#!/usr/bin/env bash
# Deploy Kitframe on the shared Hetzner host (build + up), same style as gathered-brain.
# Postgres is external — set DATABASE_URL in .env.
# Run from the repo root: ./scripts/deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-infra/docker/docker-compose.prod.yml}"
COMPOSE=(
  docker compose
  --project-directory "$ROOT"
  -f "$COMPOSE_FILE"
  --env-file "$ROOT/.env"
)

# Read KEY=value from .env without `source` (values like EMAIL_FROM="Name <a@b>" break bash).
env_get() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" .env | tail -n1 || true)"
  [[ -n "$line" ]] || return 0
  line="${line#*=}"
  line="${line%$'\r'}"
  if [[ "$line" == \"*\" ]]; then
    line="${line#\"}"
    line="${line%\"}"
  elif [[ "$line" == \'*\' ]]; then
    line="${line#\'}"
    line="${line%\'}"
  fi
  printf '%s' "$line"
}

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing — copy infra/env/production.example to .env and fill secrets." >&2
  exit 1
fi

DOMAIN="$(env_get DOMAIN)"
DATABASE_URL="$(env_get DATABASE_URL)"
JWT_SECRET="$(env_get JWT_SECRET)"
API_HOST_PORT="$(env_get KITFRAME_API_HOST_PORT)"
API_HOST_PORT="${API_HOST_PORT:-18080}"

if [[ -z "$DOMAIN" ]]; then
  echo "ERROR: DOMAIN is required in .env" >&2
  exit 1
fi
if [[ -z "$DATABASE_URL" ]]; then
  echo "ERROR: DATABASE_URL is required in .env (external Postgres)." >&2
  exit 1
fi
if [[ -z "$JWT_SECRET" ]] || [[ ${#JWT_SECRET} -lt 32 ]]; then
  echo "ERROR: JWT_SECRET missing or shorter than 32 characters." >&2
  exit 1
fi

echo "==> Building images..."
"${COMPOSE[@]}" build

echo "==> Running migrations against external Postgres"
"${COMPOSE[@]}" run --rm --no-deps api kitframe migrate

echo "==> Starting stack (api + worker + web)"
"${COMPOSE[@]}" up -d --remove-orphans

echo "==> Container status"
"${COMPOSE[@]}" ps -a

echo "==> Waiting for API health on 127.0.0.1:${API_HOST_PORT}"
for i in $(seq 1 45); do
  if curl -fsS "http://127.0.0.1:${API_HOST_PORT}/api/v1/healthz" >/dev/null 2>&1; then
    echo "API healthy."
    if [[ "${DEPLOY_SMOKE:-0}" == "1" ]]; then
      curl -fsS "http://127.0.0.1:${API_HOST_PORT}/api/v1/readyz" >/dev/null
      echo "Smoke OK"
    fi
    echo "Deploy OK → https://${DOMAIN}"
    echo "Local: http://127.0.0.1:${API_HOST_PORT}/api/v1/healthz"
    exit 0
  fi
  sleep 2
done

echo "ERROR: API did not become healthy in time." >&2
"${COMPOSE[@]}" logs --tail=80 api >&2 || true
exit 1
