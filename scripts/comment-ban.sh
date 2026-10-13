#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAIL=0

check_file() {
  local file="$1"
  local base
  base="$(basename "$file")"
  if [[ "$base" == "next-env.d.ts" ]]; then
    return 0
  fi
  local ext="${file##*.}"
  local hits=""
  case "$ext" in
    go)
      hits=$(rg -n --no-heading -e '^\s*//' -e '^\s*/\*' "$file" | rg -v '^\d+:\s*//go:' || true)
      ;;
    py)
      hits=$(rg -n --no-heading -e '^\s*#' "$file" || true)
      ;;
    ts|tsx|js|jsx)
      hits=$(rg -n --no-heading -e '^\s*//' -e '^\s*/\*' -e '<!--' -e '\{\s*/\*' "$file" || true)
      ;;
    css)
      hits=$(rg -n --no-heading -e '^\s*/\*' "$file" || true)
      ;;
    sql)
      hits=$(rg -n --no-heading -e '^\s*--' -e '^\s*/\*' "$file" || true)
      ;;
    tf)
      hits=$(rg -n --no-heading -e '^\s*#' -e '^\s*/\*' "$file" || true)
      ;;
    *)
      return 0
      ;;
  esac
  if [[ -n "$hits" ]]; then
    echo "COMMENT_BAN_VIOLATION: $file"
    echo "$hits"
    FAIL=1
  fi
}

while IFS= read -r -d '' file; do
  case "$file" in
    */node_modules/*|*/.next/*|*/.venv/*|*/__pycache__/*|*/dist/*|*/vendor/*|*/generated/*)
      continue
      ;;
  esac
  check_file "$file"
done < <(find "$ROOT/apps" "$ROOT/packages" "$ROOT/migrations" "$ROOT/infra/terraform" -type f \( \
  -name '*.go' -o -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' \
  -o -name '*.css' -o -name '*.sql' -o -name '*.tf' \
\) -print0 2>/dev/null)

if [[ "$FAIL" -ne 0 ]]; then
  echo "Comment ban failed"
  exit 1
fi

echo "Comment ban passed"
