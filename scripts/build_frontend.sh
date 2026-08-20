#!/usr/bin/env bash
# Build Vue frontend into frontend/dist (required before serving the SPA).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js 20+ and retry." >&2
  exit 1
fi

if [[ ! -d node_modules ]]; then
  echo "=== npm install (first time) ==="
  npm ci
fi

echo "=== npm run build ==="
npm run build
echo "Frontend built: $ROOT/frontend/dist"
