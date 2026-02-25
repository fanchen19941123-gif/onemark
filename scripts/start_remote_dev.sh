#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${ROOT_DIR}/output/dev-logs"
MOBILE_DIR="${ROOT_DIR}/mobile"
NPM_GLOBAL_PREFIX="${NPM_GLOBAL_PREFIX:-$HOME/.npm-global}"
EXPO_PORT="${EXPO_PORT:-8081}"

extract_tunnel_url() {
  local log_file="$1"
  python3 - "$log_file" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print("")
    raise SystemExit(0)

data = path.read_bytes()
matches = re.findall(rb"https://[-a-zA-Z0-9]+\.trycloudflare\.com", data)
if not matches:
    print("")
    raise SystemExit(0)
print(matches[-1].decode("utf-8", errors="ignore"))
PY
}

echo "[0/3] stopping old mobile bundler processes..."
pkill -f "expo start" >/dev/null 2>&1 || true
pkill -f "node.*@expo/cli" >/dev/null 2>&1 || true
if command -v lsof >/dev/null 2>&1; then
  pids="$(lsof -ti "tcp:${EXPO_PORT}" 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo "${pids}" | xargs kill >/dev/null 2>&1 || true
  fi
fi

"${SCRIPT_DIR}/start_backend_tunnel.sh"

TUNNEL_URL="$(extract_tunnel_url "${LOG_DIR}/cloudflared.log")"
if [[ -z "${TUNNEL_URL}" ]]; then
  echo "[ERROR] Tunnel URL not found in ${LOG_DIR}/cloudflared.log"
  echo "Retry in 2-3 seconds or check cloudflared log."
  exit 1
fi

echo "[INFO] Launching mobile with public backend: ${TUNNEL_URL}"
cd "${MOBILE_DIR}"
export NPM_CONFIG_PREFIX="${NPM_GLOBAL_PREFIX}"
export PATH="${NPM_GLOBAL_PREFIX}/bin:${PATH}"
export NODE_PATH="${NPM_GLOBAL_PREFIX}/lib/node_modules${NODE_PATH:+:${NODE_PATH}}"
export EXPO_NO_DEPENDENCY_VALIDATION=1

if ! npm ls -g @expo/ngrok --depth=0 >/dev/null 2>&1; then
  echo "[INFO] Installing @expo/ngrok to ${NPM_GLOBAL_PREFIX} ..."
  npm install -g @expo/ngrok@^4.1.0
fi

export EXPO_PUBLIC_API_BASE_URL="${TUNNEL_URL}"
exec npm run start -- --tunnel --clear --port "${EXPO_PORT}"
