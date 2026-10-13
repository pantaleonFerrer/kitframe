#!/usr/bin/env bash
# Deploy Kitframe on the shared Hetzner host (build + up), same style as gathered-brain.
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

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing — copy infra/env/production.example to .env and fill secrets." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
# shellcheck source=/dev/null
source .env
set +a

if [[ -z "${DOMAIN:-}" ]]; then
  echo "ERROR: DOMAIN is required in .env" >&2
  exit 1
fi
if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  echo "ERROR: POSTGRES_PASSWORD is required in .env" >&2
  exit 1
fi
if [[ -z "${JWT_SECRET:-}" ]] || [[ ${#JWT_SECRET} -lt 32 ]]; then
  echo "ERROR: JWT_SECRET missing or shorter than 32 characters." >&2
  exit 1
fi

API_HOST_PORT="${KITFRAME_API_HOST_PORT:-18080}"

echo "==> Building images..."
"${COMPOSE[@]}" build

echo "==> Starting Postgres"
"${COMPOSE[@]}" up -d postgres
for i in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T postgres pg_isready -U "${POSTGRES_USER:-kitframe}" -d "${POSTGRES_DB:-kitframe}" >/dev/null 2>&1; then
    break
  fi
  if [[ "$i" -eq 30 ]]; then
    echo "ERROR: Postgres did not become ready." >&2
    exit 1
  fi
  sleep 1
done

echo "==> Running migrations"
"${COMPOSE[@]}" run --rm --no-deps api kitframe migrate

echo "==> Starting stack"
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
