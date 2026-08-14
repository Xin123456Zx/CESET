#!/bin/bash
# Start CESET locally: Flask backend on 127.0.0.1:5001 + Vite frontend on localhost:5173.
# Requires: Python env with backend/requirements.txt installed (CUDA GPU for field
# generation) and `npm install` done inside frontend/. Ctrl+C stops both.
set -e
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

(cd "$ROOT/backend" && python server.py) &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null' EXIT

cd "$ROOT/frontend"
npm run dev
