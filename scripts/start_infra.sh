#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Docker Rootless (optional — copy scripts/docker_rootless.env.example if needed)
if [[ -f "$ROOT/scripts/docker_rootless.env" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/scripts/docker_rootless.env"
else
  echo "Tip: 使用 rootless Docker 时，可复制 scripts/docker_rootless.env.example → docker_rootless.env"
fi

echo "Docker: $DOCKER_HOST"
docker info >/dev/null 2>&1 || {
  echo "Rootless Docker not running. Try: systemctl --user start docker.service" >&2
  exit 1
}

echo "Starting PostgreSQL + Redis..."
docker compose up -d

echo "Waiting for services..."
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U boltz -d boltzfold >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "Infrastructure ready."
echo "  PostgreSQL: localhost:5433"
echo "  Redis:      localhost:6380"
echo "Next: bash scripts/start_platform.sh"
