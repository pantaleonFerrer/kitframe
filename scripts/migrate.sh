#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATABASE_URL="${DATABASE_URL:-postgres://kitframe:kitframe@localhost:5433/kitframe?sslmode=disable}"

if ! command -v migrate >/dev/null 2>&1; then
  if [[ -x "${HOME}/go/bin/migrate" ]]; then
    export PATH="${HOME}/go/bin:${PATH}"
  elif [[ -x "$(go env GOPATH 2>/dev/null)/bin/migrate" ]]; then
    export PATH="$(go env GOPATH)/bin:${PATH}"
  fi
fi

if ! command -v migrate >/dev/null 2>&1; then
  echo "golang-migrate CLI (migrate) is required: https://github.com/golang-migrate/migrate"
  exit 1
fi

migrate -path "${ROOT}/migrations" -database "${DATABASE_URL}" up
echo "Migrations applied against DATABASE_URL"
