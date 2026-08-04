#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Docker Rootless (no sudo / docker group required)
# shellcheck disable=SC1091
source "$ROOT/scripts/docker_rootless.env"

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
