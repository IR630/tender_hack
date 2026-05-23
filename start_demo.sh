#!/usr/bin/env bash
# Hybrid demo stand: Docker (frontend + infra) + host FastAPI with Ozon nodriver.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${ROOT}/docker-compose.hybrid.yml"
API_PID=""

cleanup() {
  echo ""
  echo "=== Остановка демо-стенда ==="
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    echo "[stop] uvicorn PID ${API_PID}"
    kill "${API_PID}" 2>/dev/null || true
    wait "${API_PID}" 2>/dev/null || true
  fi
  if [[ -f "${COMPOSE_FILE}" ]]; then
    docker compose -f "${COMPOSE_FILE}" down --remove-orphans 2>/dev/null || true
  fi
  if [[ -x "${ROOT}/kill_zombies.sh" ]]; then
    "${ROOT}/kill_zombies.sh"
  fi
  echo "Готово."
}

trap cleanup EXIT INT TERM

echo "=== Tender Hack — гибридный демо-стенд ==="

echo "[1/2] Docker: frontend, Redis, SearXNG, MeiliSearch…"
docker compose -f "${COMPOSE_FILE}" up -d --build

echo "[2/2] Host API: uv sync + uvicorn на http://127.0.0.1:8000"
cd "${ROOT}/backend"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv не найден — https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

uv sync

export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export SEARXNG_URL="${SEARXNG_URL:-http://127.0.0.1:8080}"
export MEILI_URL="${MEILI_URL:-http://127.0.0.1:7700}"
export MEILI_MASTER_KEY="${MEILI_MASTER_KEY:-dev-master-key}"
export OZON_USE_BROWSER="${OZON_USE_BROWSER:-true}"
export OZON_BROWSER_CACHE_ENABLED="${OZON_BROWSER_CACHE_ENABLED:-false}"
export OZON_BROWSER_MAX_RETRIES="${OZON_BROWSER_MAX_RETRIES:-1}"
export OZON_BROWSER_TOTAL_TIMEOUT_SECONDS="${OZON_BROWSER_TOTAL_TIMEOUT_SECONDS:-45}"
export OZON_BROWSER_WAIT_SECONDS="${OZON_BROWSER_WAIT_SECONDS:-30}"
export OZON_BROWSER_WARMUP_HOME="${OZON_BROWSER_WARMUP_HOME:-true}"
export OZON_ENRICH_ENABLED="${OZON_ENRICH_ENABLED:-false}"
export OZON_ENRICH_DELAY_SECONDS="${OZON_ENRICH_DELAY_SECONDS:-12}"
export OZON_ENRICH_WAIT_SECONDS="${OZON_ENRICH_WAIT_SECONDS:-15}"
export OZON_PIPELINE_TIMEOUT_SECONDS="${OZON_PIPELINE_TIMEOUT_SECONDS:-180}"

export OTHER_DDG_ENABLED="${OTHER_DDG_ENABLED:-true}"
export OTHER_YAHOO_ENABLED="${OTHER_YAHOO_ENABLED:-true}"
export OTHER_BING_FALLBACK_ENABLED="${OTHER_BING_FALLBACK_ENABLED:-false}"
export OTHER_SEARCH_TIMEOUT_SECONDS="${OTHER_SEARCH_TIMEOUT_SECONDS:-45}"
export OTHER_CACHE_ENABLED="${OTHER_CACHE_ENABLED:-false}"

# Wildberries proxy — из корневого .env (если не задано в окружении)
if [[ -z "${WB_PROXY:-}" && -f "${ROOT}/.env" ]]; then
  WB_PROXY="$(grep -E '^WB_PROXY=' "${ROOT}/.env" | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
  export WB_PROXY
fi
export WB_PROXY_MAX_RETRIES="${WB_PROXY_MAX_RETRIES:-15}"
export WB_PROXY_STICKY_SESSION="${WB_PROXY_STICKY_SESSION:-false}"
if [[ -n "${WB_PROXY:-}" ]]; then
  echo "WB_PROXY configured (pool proxy enabled)"
else
  echo "WARN: WB_PROXY not set — Wildberries will use direct IP"
fi

run_api() {
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
}

if [[ -n "${DISPLAY:-}" ]]; then
  echo "DISPLAY=${DISPLAY} — используем реальный дисплей"
  run_api &
else
  echo "DISPLAY не задан — запуск через xvfb-run"
  if ! command -v xvfb-run >/dev/null 2>&1; then
    echo "ERROR: установите xvfb (pacman -S xorg-server-xvfb)"
    exit 1
  fi
  xvfb-run -a uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 &
fi

API_PID=$!
sleep 2

if ! kill -0 "${API_PID}" 2>/dev/null; then
  echo "ERROR: API не запустился"
  exit 1
fi

echo ""
echo "Стенд готов:"
echo "  UI:  http://127.0.0.1:5173"
echo "  API: http://127.0.0.1:8000/health"
echo ""
echo "Ctrl+C — остановить всё"
echo ""

wait "${API_PID}"
