#!/usr/bin/env zsh
set -euo pipefail

ROOT="/Users/kusumathatavarthi/jira_ai_chatbot_artifacts"
PYTHON="/Users/kusumathatavarthi/.pyenv/versions/3.11.9/bin/python"
API_HOST="127.0.0.1"
API_PORT="8000"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  if [[ -n "$FRONTEND_PID" ]]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$BACKEND_PID" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

cd "$ROOT"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required but not found. Please install Node.js."
  exit 1
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  cd "$ROOT/frontend"
  npm install
  cd "$ROOT"
fi

echo "Starting FastAPI backend on http://$API_HOST:$API_PORT ..."
PYTHONPATH="$ROOT" "$PYTHON" -m uvicorn backend.api:app --host "$API_HOST" --port "$API_PORT" > "$ROOT/backend.log" 2>&1 &
BACKEND_PID=$!

sleep 2
if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
  echo "Backend failed to start. Check: $ROOT/backend.log"
  exit 1
fi

echo "Starting React frontend (Vite)..."
cd "$ROOT/frontend"
npm run dev > "$ROOT/frontend.log" 2>&1 &
FRONTEND_PID=$!

sleep 2
if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
  echo "Frontend failed to start. Check: $ROOT/frontend.log"
  exit 1
fi

cat <<EOF

Services started:
- Backend: http://$API_HOST:$API_PORT
- Frontend: check Vite URL in $ROOT/frontend.log (usually http://localhost:5173)

Logs:
- $ROOT/backend.log
- $ROOT/frontend.log

Press Ctrl+C to stop both.
EOF

wait "$FRONTEND_PID"
