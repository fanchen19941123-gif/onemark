#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
MOBILE_DIR="${ROOT_DIR}/mobile"
LOG_DIR="${ROOT_DIR}/output/dev-logs"

BACKEND_PORT="${BACKEND_PORT:-8000}"
LOCAL_IP="${LOCAL_IP:-}"

if [[ -z "${LOCAL_IP}" ]]; then
  LOCAL_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [[ -z "${LOCAL_IP}" ]]; then
  LOCAL_IP="$(ipconfig getifaddr en1 2>/dev/null || true)"
fi
if [[ -z "${LOCAL_IP}" ]]; then
  LOCAL_IP="127.0.0.1"
  echo "[WARN] Could not detect LAN IP; fallback to ${LOCAL_IP}"
fi

API_BASE_URL="${EXPO_PUBLIC_API_BASE_URL:-http://${LOCAL_IP}:${BACKEND_PORT}}"

mkdir -p "${LOG_DIR}"

echo "[1/4] Stopping old processes..."
pkill -f "uvicorn app.main:app" >/dev/null 2>&1 || true
pkill -f "expo start" >/dev/null 2>&1 || true

if [[ ! -f "${BACKEND_DIR}/.venv/bin/activate" ]]; then
  echo "[ERROR] Backend venv not found: ${BACKEND_DIR}/.venv"
  echo "Run: cd ${BACKEND_DIR} && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

echo "[2/4] Starting backend on :${BACKEND_PORT} ..."
(
  cd "${BACKEND_DIR}"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  nohup uvicorn app.main:app --reload --host 0.0.0.0 --port "${BACKEND_PORT}" > "${LOG_DIR}/backend.log" 2>&1 &
  echo "$!" > "${LOG_DIR}/backend.pid"
)

echo "[3/4] Waiting backend health..."
for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -fsS "http://127.0.0.1:${BACKEND_PORT}/healthz" >/dev/null 2>&1; then
  echo "[ERROR] Backend failed to start. See log: ${LOG_DIR}/backend.log"
  exit 1
fi

echo "[OK] Backend ready: http://127.0.0.1:${BACKEND_PORT}/healthz"
echo "[INFO] API base url for mobile: ${API_BASE_URL}"
echo "[INFO] Backend log: ${LOG_DIR}/backend.log"
echo "[INFO] To stop backend only: kill \$(cat ${LOG_DIR}/backend.pid)"

echo "[4/4] Starting mobile (Expo) ..."
cd "${MOBILE_DIR}"
export EXPO_PUBLIC_API_BASE_URL="${API_BASE_URL}"
exec npm run start -- --clear
