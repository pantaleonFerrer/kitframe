#!/usr/bin/env bash
# Demo stack: load repo .env (BFL + AWS S3). Do NOT force fake/MinIO.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

COMPOSE=(docker compose -f infra/docker/docker-compose.yml)
export APP_ENV="${APP_ENV:-local}"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://kitframe:kitframe@localhost:5433/kitframe}"
export JWT_SECRET="${JWT_SECRET:-local-dev-jwt-secret-change-me-now!!}"
export SEED_PASSWORDS="${SEED_PASSWORDS:-true}"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8080/api/v1}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:3000}"

# Ensure empty S3_ENDPOINT stays empty (AWS mode) — do not default to MinIO here
if [[ -z "${S3_ENDPOINT:-}" ]]; then
  export S3_ENDPOINT=""
fi

PIDS=()
STOPPING=0

cleanup() {
  if [[ "$STOPPING" -eq 1 ]]; then
    return
  fi
  STOPPING=1
  echo
  echo "Stopping Kitframe demo…"
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      pkill -P "$pid" 2>/dev/null || true
      kill "$pid" 2>/dev/null || true
    fi
  done
  pkill -f "kitframe api" 2>/dev/null || true
  pkill -f "kitframe worker" 2>/dev/null || true
  pkill -f "next dev" 2>/dev/null || true
  wait 2>/dev/null || true
  echo "Stopped."
  exit 0
}

trap cleanup INT TERM EXIT

prefix() {
  local name="$1"
  shift
  "$@" > >(sed -u "s/^/[$name] /") 2>&1 &
  PIDS+=($!)
}

echo "→ Infra (postgres + mailpit; MinIO optional if S3_ENDPOINT set)"
if [[ -n "${S3_ENDPOINT:-}" ]]; then
  "${COMPOSE[@]}" up -d postgres minio minio-init mailpit
else
  "${COMPOSE[@]}" up -d postgres mailpit
fi

echo "→ API venv + deps"
(
  cd apps/api
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -e ".[dev]" -q
)

echo "→ Migrate + seed (sync provider_config from .env)"
(
  cd apps/api
  # shellcheck disable=SC1091
  source .venv/bin/activate
  kitframe migrate
  kitframe seed
)

if [[ ! -d apps/web/node_modules ]]; then
  echo "→ pnpm install"
  (cd apps/web && pnpm install)
fi

echo
echo "═══════════════════════════════════════════════════"
echo "  DEMO MODE"
echo "  IMAGE_PROVIDER=${IMAGE_PROVIDER:-?}  LLM=${LLM_PROVIDER:-?}"
echo "  S3=${S3_BUCKET:-?} @ ${S3_REGION:-?}  endpoint=${S3_ENDPOINT:-AWS}"
echo "  Web  http://localhost:3000"
echo "  Login owner@kitframe.local / Kitframe-dev-2026!"
echo "  Guion: producto FCB-DEMO-002 · fotos reales · Generar"
echo "═══════════════════════════════════════════════════"
echo

trap - EXIT
trap cleanup INT TERM

prefix api bash -lc "
  cd '$ROOT/apps/api' && source .venv/bin/activate && \
  exec kitframe api --host 0.0.0.0 --port 8080
"

prefix worker bash -lc "
  cd '$ROOT/apps/api' && source .venv/bin/activate && \
  exec kitframe worker
"

prefix web bash -lc "
  cd '$ROOT/apps/web' && exec pnpm dev
"

while true; do
  for pid in "${PIDS[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Un proceso terminó (pid=$pid). Cerrando el resto…"
      cleanup
    fi
  done
  sleep 1
done
