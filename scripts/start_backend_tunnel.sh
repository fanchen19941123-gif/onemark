#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
LOG_DIR="${ROOT_DIR}/output/dev-logs"
BACKEND_PORT="${BACKEND_PORT:-8000}"
TUNNEL_PROTOCOL="${TUNNEL_PROTOCOL:-http2}"
BACKEND_RELOAD="${BACKEND_RELOAD:-0}"

mkdir -p "${LOG_DIR}"

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

has_registered_connection() {
  local log_file="$1"
  python3 - "$log_file" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print("0")
    raise SystemExit(0)
data = path.read_bytes()
print("1" if b"Registered tunnel connection" in data else "0")
PY
}

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "[ERROR] cloudflared not found."
  echo "Install: brew install cloudflared"
  exit 1
fi

if [[ ! -f "${BACKEND_DIR}/.venv/bin/activate" ]]; then
  echo "[ERROR] backend venv not found: ${BACKEND_DIR}/.venv"
  exit 1
fi

echo "[1/3] stopping old backend/tunnel processes..."
pkill -f "uvicorn app.main:app" >/dev/null 2>&1 || true
pkill -f "cloudflared tunnel --url http://127.0.0.1:${BACKEND_PORT}" >/dev/null 2>&1 || true

echo "[2/3] starting backend..."
(
  cd "${BACKEND_DIR}"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  UVICORN_ARGS=(app.main:app --host 0.0.0.0 --port "${BACKEND_PORT}")
  if [[ "${BACKEND_RELOAD}" == "1" ]]; then
    UVICORN_ARGS+=(--reload)
  fi
  nohup uvicorn "${UVICORN_ARGS[@]}" > "${LOG_DIR}/backend.log" 2>&1 &
  echo "$!" > "${LOG_DIR}/backend.pid"
)

for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -fsS "http://127.0.0.1:${BACKEND_PORT}/healthz" >/dev/null 2>&1; then
  echo "[ERROR] backend failed to start, see ${LOG_DIR}/backend.log"
  exit 1
fi

echo "[3/3] starting cloudflared tunnel..."
nohup cloudflared tunnel --url "http://127.0.0.1:${BACKEND_PORT}" --protocol "${TUNNEL_PROTOCOL}" > "${LOG_DIR}/cloudflared.log" 2>&1 &
echo "$!" > "${LOG_DIR}/cloudflared.pid"

TUNNEL_URL=""
for _ in {1..80}; do
  TUNNEL_URL="$(extract_tunnel_url "${LOG_DIR}/cloudflared.log")"
  if [[ -n "${TUNNEL_URL}" ]]; then
    break
  fi
  sleep 0.5
done

if [[ -z "${TUNNEL_URL}" ]]; then
  echo "[WARN] tunnel started but URL not parsed yet."
  echo "Check log: ${LOG_DIR}/cloudflared.log"
  exit 0
fi

registered=0
for _ in {1..60}; do
  if [[ -f "${LOG_DIR}/cloudflared.pid" ]]; then
    pid="$(cat "${LOG_DIR}/cloudflared.pid" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && ! kill -0 "${pid}" >/dev/null 2>&1; then
      break
    fi
  fi
  if [[ "$(has_registered_connection "${LOG_DIR}/cloudflared.log")" == "1" ]]; then
    registered=1
    break
  fi
  sleep 0.5
done

if [[ "${registered}" != "1" ]]; then
  echo "[WARN] tunnel URL exists but connection not confirmed yet."
  echo "Check log: ${LOG_DIR}/cloudflared.log"
fi

echo
echo "[OK] backend local: http://127.0.0.1:${BACKEND_PORT}"
echo "[OK] backend public: ${TUNNEL_URL}"
echo
echo "Use in mobile startup:"
echo "  export EXPO_PUBLIC_API_BASE_URL=${TUNNEL_URL}"
echo "  cd ${ROOT_DIR}/mobile && npm run start -- --tunnel --clear"
