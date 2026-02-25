#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"

if [[ ! -f "${BACKEND_DIR}/.venv/bin/activate" ]]; then
  echo "[ERROR] Missing backend virtual env: ${BACKEND_DIR}/.venv"
  echo "Create it with:"
  echo "  cd ${BACKEND_DIR}"
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

PLATFORMS="${PLATFORMS:-douyin,xiaohongshu}"
DOUYIN_FAVORITES_URL="${DOUYIN_FAVORITES_URL:-https://www.douyin.com/user/self?from_tab_name=main&showTab=favorite_collection}"
XHS_FAVORITES_URL="${XHS_FAVORITES_URL:-https://www.xiaohongshu.com/user/profile/5b6d964d6b58b73cf17548e4?tab=fav&subTab=note}"

echo "[INFO] Running local user-agent smoke test"
echo "[INFO] Platforms: ${PLATFORMS}"
echo "[INFO] Douyin favorites URL: ${DOUYIN_FAVORITES_URL}"
echo "[INFO] XHS favorites URL: ${XHS_FAVORITES_URL}"
echo
echo "[TIP] Keep Chrome logged in for Douyin/Xiaohongshu."

cd "${BACKEND_DIR}"
# shellcheck disable=SC1091
source .venv/bin/activate

DOUYIN_FAVORITES_URL="${DOUYIN_FAVORITES_URL}" \
XHS_FAVORITES_URL="${XHS_FAVORITES_URL}" \
PYTHONPATH="$(pwd)" \
python scripts/smoke_flow.py --platforms "${PLATFORMS}"
