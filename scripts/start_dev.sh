#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--tunnel" ]]; then
  shift
  exec "${SCRIPT_DIR}/start_remote_dev.sh" "$@"
fi

exec "${SCRIPT_DIR}/restart_dev.sh" "$@"
