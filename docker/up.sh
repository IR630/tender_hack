#!/usr/bin/env bash
# Start full stack in Docker with host X11 for Ozon nodriver (same as ./start_demo.sh browser path).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/docker/docker-compose.yml"

export DISPLAY="${DISPLAY:-:0}"

if [ -S "/tmp/.X11-unix/X${DISPLAY#*:}" ] 2>/dev/null || [ -d /tmp/.X11-unix ]; then
  echo "X11 detected — Ozon browser will use host display ${DISPLAY}"
  if command -v xhost >/dev/null 2>&1; then
    xhost +local:docker >/dev/null 2>&1 || xhost +local: >/dev/null 2>&1 || true
  fi
else
  echo "No X11 socket — Ozon will use Xvfb inside the API container (may hit WAF)"
  export DISPLAY=":99"
fi

cd "${ROOT}"
exec docker compose -f "${COMPOSE_FILE}" up --build "$@"
