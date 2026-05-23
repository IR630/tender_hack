#!/bin/sh
set -eu

if [ "${OZON_USE_BROWSER:-false}" = "true" ]; then
  export DISPLAY="${DISPLAY:-:99}"
  case "${DISPLAY}" in
    :99|:99.*)
      if ! pgrep -x Xvfb >/dev/null 2>&1; then
        echo "Starting Xvfb on ${DISPLAY} for Ozon nodriver…"
        Xvfb "${DISPLAY}" -screen 0 1920x1080x24 -nolisten tcp &
        sleep 1
      fi
      ;;
    *)
      echo "Using host DISPLAY=${DISPLAY} for Ozon nodriver (no Xvfb)"
      ;;
  esac
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
