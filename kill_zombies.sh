#!/usr/bin/env bash
# Kill zombie Chromium / nodriver / Xvfb processes after crashes or restarts.
set -uo pipefail

echo "=== Ozon browser zombie killer ==="

kill_pattern() {
  local label="$1"
  local pattern="$2"
  local pids
  pids=$(pgrep -f "$pattern" 2>/dev/null || true)
  if [[ -z "$pids" ]]; then
    echo "[skip] $label — no processes"
    return 0
  fi
  echo "[kill] $label — PIDs: $pids"
  pkill -9 -f "$pattern" 2>/dev/null || true
  sleep 0.3
}

# Xvfb virtual displays
kill_pattern "Xvfb" "[X]vfb"

# nodriver / undetected-chromedriver temp profiles
kill_pattern "nodriver" "nodriver"
kill_pattern "uc_" "/tmp/uc_"

# Chromium / Chrome instances (demo server — aggressive cleanup)
kill_pattern "chromium" "chromium"
kill_pattern "chrome" "chrome.*--remote-debugging"
kill_pattern "chrome-sandbox" "chrome-sandbox"

echo "=== Remaining (if any) ==="
pgrep -af 'chromium|chrome|Xvfb|nodriver' 2>/dev/null || echo "All clean."

echo "Done."
