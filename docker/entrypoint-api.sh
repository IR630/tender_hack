#!/bin/sh
set -eu

start_xvfb() {
  display="${1:-:99}"
  if pgrep -x Xvfb >/dev/null 2>&1; then
    echo "Xvfb already running for DISPLAY=${display}"
    return 0
  fi
  echo "Starting Xvfb on ${display} for Ozon nodriver…"
  Xvfb "${display}" -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
  sleep 2
}

if [ "${OZON_USE_BROWSER:-false}" = "true" ]; then
  export DISPLAY="${DISPLAY:-:99}"

  case "${DISPLAY}" in
    :99|:99.*)
      start_xvfb "${DISPLAY}"
      ;;
    *)
      if [ -S "/tmp/.X11-unix/X${DISPLAY#*:}" ] 2>/dev/null || [ -d /tmp/.X11-unix ]; then
        echo "Using host X11 DISPLAY=${DISPLAY} for Ozon nodriver"
      else
        echo "WARNING: X11 socket not found, falling back to Xvfb :99"
        export DISPLAY=":99"
        start_xvfb ":99"
      fi
      ;;
  esac

  export OZON_BROWSER_HEADLESS="${OZON_BROWSER_HEADLESS:-false}"
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
