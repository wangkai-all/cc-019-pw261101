#!/usr/bin/env bash
# Start backend + frontend together for local development.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

.venv/bin/uvicorn app.main:app --port 8000 &
API_PID=$!

cleanup() { kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT

cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  npm install --cache "$ROOT/frontend/.npm-cache"
fi
npm run dev
