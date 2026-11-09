#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-${ROOT_DIR}/.venv/bin/python}"
FRONTEND_DIR="${ROOT_DIR}/frontend"
VM_IP="${EB_VM_IP:-127.0.0.1}"
VITE_API_BASE="${VITE_API_BASE:-http://${VM_IP}:8000}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Python environment not found at ${PYTHON}."
  echo "Create it and install backend requirements before running this script."
  exit 1
fi

if ! command -v ip >/dev/null 2>&1 ||
  ! ip netns list 2>/dev/null | awk '{ print $1 }' | grep -Eq '^client[1-9][0-9]*$' ||
  [[ ! -d /sys/class/net/br-lab ]]; then
  echo "Linux namespace lab not found."
  echo "Set it up with: sudo bash scripts/setup_gateway.sh"
  exit 1
fi

if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
  echo "Frontend dependencies are missing. Run: cd frontend && npm ci"
  exit 1
fi

for port in 8000 5173; do
  if ! "$PYTHON" -c \
    'import socket, sys; socket.socket().bind(("0.0.0.0", int(sys.argv[1])))' \
    "$port" 2>/dev/null; then
    echo "Port ${port} is already in use; stop its service before starting the runner."
    exit 1
  fi
done

backend_pid=""
frontend_pid=""
cleanup() {
  if [[ -n "$frontend_pid" ]]; then
    kill "$frontend_pid" 2>/dev/null || true
    wait "$frontend_pid" 2>/dev/null || true
  fi
  if [[ -n "$backend_pid" ]]; then
    kill "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "Starting product API at http://0.0.0.0:8000"
(
  cd "$ROOT_DIR"
  export EB_LAB_INGEST=1
  export PYTHONPATH="${ROOT_DIR}:${ROOT_DIR}/backend${PYTHONPATH:+:${PYTHONPATH}}"
  exec "$PYTHON" -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
) &
backend_pid=$!

echo "Starting dashboard at http://0.0.0.0:5173"
echo "Dashboard API base: ${VITE_API_BASE}"
(
  cd "$FRONTEND_DIR"
  export VITE_API_BASE
  exec ./node_modules/.bin/vite --host 0.0.0.0 --strictPort
) &
frontend_pid=$!

wait -n "$backend_pid" "$frontend_pid"
