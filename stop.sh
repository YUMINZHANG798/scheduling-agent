#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

stop_pid_file() {
  local name="$1"
  local file="$2"
  if [[ ! -f "$file" ]]; then
    return
  fi

  local pid
  pid="$(tr -d '[:space:]' < "$file")"
  if is_running "$pid"; then
    echo "Stopping $name, PID $pid..."
    kill "$pid" 2>/dev/null || true
    for _ in {1..20}; do
      if ! is_running "$pid"; then
        break
      fi
      sleep 0.25
    done
    if is_running "$pid"; then
      echo "$name PID $pid is still running; please stop it manually if needed."
    fi
  fi
  rm -f "$file"
}

stop_port() {
  local name="$1"
  local port="$2"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return
  fi
  echo "Stopping process(es) on $name port $port: $pids"
  kill $pids 2>/dev/null || true
}

stop_pid_file "frontend" "$FRONTEND_PID_FILE"
stop_pid_file "backend" "$BACKEND_PID_FILE"

stop_port "frontend" 5173
stop_port "backend" 8000

echo "Project stopped."
