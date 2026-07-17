#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
LOG_DIR="$RUNTIME_DIR/logs"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"

mkdir -p "$LOG_DIR"

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

pid_from_file() {
  local file="$1"
  [[ -f "$file" ]] && tr -d '[:space:]' < "$file" || true
}

ensure_port_free() {
  local port="$1"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Run ./stop.sh first, or stop the process manually."
    lsof -nP -iTCP:"$port" -sTCP:LISTEN
    exit 1
  fi
}

wait_for_url() {
  local url="$1"
  local name="$2"
  for _ in {1..40}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is ready: $url"
      return 0
    fi
    sleep 0.25
  done
  echo "$name started, but readiness check timed out. Check logs under $LOG_DIR."
}

start_backend() {
  local existing_pid
  existing_pid="$(pid_from_file "$BACKEND_PID_FILE")"
  if is_running "$existing_pid"; then
    echo "Backend is already running, PID $existing_pid"
    return
  fi

  ensure_port_free 8000
  echo "Starting backend..."
  nohup bash -c "cd '$ROOT_DIR/backend' && exec env PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000" \
    > "$LOG_DIR/backend.log" 2>&1 &
  echo "$!" > "$BACKEND_PID_FILE"
  wait_for_url "http://127.0.0.1:8000/health" "Backend"
}

start_frontend() {
  local existing_pid
  existing_pid="$(pid_from_file "$FRONTEND_PID_FILE")"
  if is_running "$existing_pid"; then
    echo "Frontend is already running, PID $existing_pid"
    return
  fi

  ensure_port_free 5173
  echo "Starting frontend..."
  nohup bash -c "cd '$ROOT_DIR/frontend' && exec npm run dev -- --host 127.0.0.1" \
    > "$LOG_DIR/frontend.log" 2>&1 &
  echo "$!" > "$FRONTEND_PID_FILE"
  wait_for_url "http://127.0.0.1:5173/" "Frontend"
}

start_backend
start_frontend

echo
echo "Project started."
echo "Frontend: http://127.0.0.1:5173/"
echo "Backend:  http://127.0.0.1:8000"
echo "Logs:     $LOG_DIR"
