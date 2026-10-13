#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/packages/shared-types"
OPENAPI_URL="${OPENAPI_URL:-http://localhost:8080/openapi.json}"
OPENAPI_FILE="${OPENAPI_FILE:-}"
OUT_DIR="$PKG/src/generated"
OUT_TS="$OUT_DIR/openapi.ts"
OUT_JSON="$PKG/openapi.json"

mkdir -p "$OUT_DIR"

if [[ -n "$OPENAPI_FILE" ]]; then
  cp "$OPENAPI_FILE" "$OUT_JSON"
else
  echo "Fetching OpenAPI from $OPENAPI_URL"
  curl -fsSL "$OPENAPI_URL" -o "$OUT_JSON"
fi

echo "Generating TypeScript with openapi-typescript (devDependency in packages/shared-types)"
cd "$PKG"
if command -v pnpm >/dev/null 2>&1; then
  pnpm install --ignore-workspace --config.confirmModulesPurge=false
  pnpm exec openapi-typescript "$OUT_JSON" -o "$OUT_TS"
elif command -v npx >/dev/null 2>&1; then
  npm install --no-fund --no-audit
  npx openapi-typescript "$OUT_JSON" -o "$OUT_TS"
else
  echo "Install pnpm or npm, then openapi-typescript in packages/shared-types" >&2
  exit 1
fi

echo "Wrote $OUT_TS"
