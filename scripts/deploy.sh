#!/usr/bin/env bash
# Deploy Kitframe on the shared Hetzner host (Docker Compose + host Nginx).
# Run from the repo root: IMAGE_TAG=<sha> ./scripts/deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(
  docker compose
  --project-directory "$ROOT"
  -f infra/docker/docker-compose.prod.yml
  --env-file "$ROOT/.env"
)
IMAGE_TAG="${IMAGE_TAG:-}"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy infra/env/production.example to .env and fill secrets." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
# shellcheck source=/dev/null
source .env
set +a

if [[ -z "${IMAGE_TAG}" ]]; then
  echo "IMAGE_TAG is required (git SHA or semver tag of published images)." >&2
  exit 1
fi
export IMAGE_TAG

if [[ -z "${DOMAIN:-}" ]]; then
  echo "DOMAIN is required in .env" >&2
  exit 1
fi

API_HOST_PORT="${KITFRAME_API_HOST_PORT:-18080}"

echo "==> Pulling images (tag=${IMAGE_TAG})"
"${COMPOSE[@]}" pull api worker web postgres

echo "==> Starting Postgres"
"${COMPOSE[@]}" up -d postgres
for i in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T postgres pg_isready -U "${POSTGRES_USER:-kitframe}" -d "${POSTGRES_DB:-kitframe}" >/dev/null 2>&1; then
    break
  fi
  if [[ "$i" -eq 30 ]]; then
    echo "Postgres did not become ready." >&2
    exit 1
  fi
  sleep 1
done

echo "==> Running migrations"
"${COMPOSE[@]}" run --rm --no-deps api kitframe migrate

echo "==> Starting stack"
"${COMPOSE[@]}" up -d

echo "==> Waiting for API health on 127.0.0.1:${API_HOST_PORT}"
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${API_HOST_PORT}/api/v1/healthz" >/dev/null 2>&1; then
    echo "API healthy."
    break
  fi
  if [[ "$i" -eq 30 ]]; then
    echo "API did not become healthy in time. Check: ${COMPOSE[*]} logs api" >&2
    exit 1
  fi
  sleep 2
done

echo "==> Smoke via public domain (needs Nginx vhost)"
if curl -fsS "https://${DOMAIN}/api/v1/healthz" >/dev/null 2>&1; then
  echo "OK https://${DOMAIN}/api/v1/healthz"
else
  echo "Warning: https://${DOMAIN}/api/v1/healthz not reachable yet." >&2
  echo "Ensure infra/nginx/kitframe.conf is enabled and DNS points here." >&2
fi

echo "Deploy complete → https://${DOMAIN}"
echo "Local: http://127.0.0.1:${API_HOST_PORT}/api/v1/healthz"
