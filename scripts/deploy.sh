#!/usr/bin/env bash
# Server-side deploy script, invoked by GitHub Actions over SSH.
#
#   ./scripts/deploy.sh [all|backend|frontend]
#
# Expects the layout created by scripts/setup-ec2.sh:
#   ~/TruckDriverLog/backend   (this repo — compose + nginx live here)
#   ~/TruckDriverLog/frontend
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ROOT_DIR="$(dirname "$BACKEND_DIR")"
FRONTEND_DIR="$ROOT_DIR/frontend"
TARGET="${1:-all}"

cd "$BACKEND_DIR"

log() { printf "\n\033[1;33m==> %s\033[0m\n" "$*"; }

pull() {
  log "Pulling $1"
  git -C "$1" fetch origin main
  git -C "$1" reset --hard origin/main
}

case "$TARGET" in
  backend)
    pull "$BACKEND_DIR"
    log "Rebuilding backend services"
    docker compose build backend
    docker compose up -d backend worker beat
    # nginx caches upstream IPs at startup; restart it so it picks up the
    # recreated backend container.
    docker compose restart nginx
    ;;
  frontend)
    pull "$FRONTEND_DIR"
    log "Rebuilding frontend"
    docker compose build frontend
    docker compose up -d frontend
    docker compose restart nginx
    ;;
  all)
    pull "$BACKEND_DIR"
    pull "$FRONTEND_DIR"
    log "Rebuilding all services (serially, to keep memory peaks low)"
    docker compose build backend
    docker compose build frontend
    docker compose up -d
    ;;
  *)
    echo "Usage: $0 [all|backend|frontend]" >&2
    exit 1
    ;;
esac

log "Pruning dangling images"
docker image prune -f >/dev/null

log "Waiting for health check"
for i in $(seq 1 30); do
  if curl -fsS http://localhost/api/health/ >/dev/null 2>&1; then
    log "Deploy OK — /api/health/ responding"
    exit 0
  fi
  sleep 2
done

echo "Health check failed after deploy" >&2
docker compose ps
exit 1
