#!/usr/bin/env bash
# Kitframe local stack in one terminal. Ctrl+C stops api + worker + web.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f infra/docker/docker-compose.yml)
export APP_ENV="${APP_ENV:-local}"
export IMAGE_PROVIDER="${IMAGE_PROVIDER:-fake}"
export LLM_PROVIDER="${LLM_PROVIDER:-fake}"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://kitframe:kitframe@localhost:5433/kitframe}"
export JWT_SECRET="${JWT_SECRET:-local-dev-jwt-secret-change-me-now!!}"
export S3_ENDPOINT="${S3_ENDPOINT:-http://localhost:9000}"
export S3_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID:-kitframe}"
export S3_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY:-kitframekitframe}"
export S3_BUCKET="${S3_BUCKET:-kitframe-assets}"
export S3_USE_PATH_STYLE="${S3_USE_PATH_STYLE:-true}"
export SMTP_HOST="${SMTP_HOST:-localhost}"
export SMTP_PORT="${SMTP_PORT:-1025}"
export SEED_PASSWORDS="${SEED_PASSWORDS:-true}"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8080/api/v1}"

PIDS=()
STOPPING=0

cleanup() {
  if [[ "$STOPPING" -eq 1 ]]; then
    return
  fi
  STOPPING=1
  echo
  echo "Stopping Kitframe…"
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      # Kill the process and its children
      pkill -P "$pid" 2>/dev/null || true
      kill "$pid" 2>/dev/null || true
    fi
  done
  # Belt-and-suspenders for known children
  pkill -f "kitframe api" 2>/dev/null || true
  pkill -f "kitframe worker" 2>/dev/null || true
  pkill -f "next dev" 2>/dev/null || true
  wait 2>/dev/null || true
  echo "Stopped. (Docker sigue arriba → make down para apagarlo)"
  exit 0
}

trap cleanup INT TERM EXIT

prefix() {
  local name="$1"
  shift
  "$@" > >(sed -u "s/^/[$name] /") 2>&1 &
  PIDS+=($!)
}

echo "→ Infra (postgres, minio, mailpit)"
"${COMPOSE[@]}" up -d postgres minio minio-init mailpit

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

echo "→ Migrate + seed"
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
echo "Kitframe listo. Ctrl+C para parar api/worker/web."
echo "  Web     http://localhost:3000"
echo "  API     http://localhost:8080/api/v1"
echo "  Mailpit http://localhost:8025"
echo "  Login   owner@kitframe.local / Kitframe-dev-2026!"
echo

# Disable EXIT trap during long wait so normal child exit still cleans up via wait
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

# Stay foreground until Ctrl+C (macOS bash 3.2 has no `wait -n`)
while true; do
  for pid in "${PIDS[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Un proceso terminó (pid=$pid). Cerrando el resto…"
      cleanup
    fi
  done
  sleep 1
done
