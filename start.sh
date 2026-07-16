#!/usr/bin/env bash
# Start apiKeyConfig without opening a browser (macOS / Linux).
# Usage (from any cwd):
#   ./start.sh
#   ./start.sh --host 127.0.0.1 --port 7878
# Optional background:
#   ./start.sh --bg
#   ./start.sh --bg --host 0.0.0.0 --port 7878
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "error: neither python3 nor python found in PATH" >&2
  exit 1
fi

BG=0
ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--bg" || "$arg" == "--background" ]]; then
    BG=1
  else
    ARGS+=("$arg")
  fi
done

if [[ "$BG" -eq 1 ]]; then
  nohup "$PY" app.py --no-browser "${ARGS[@]}" >/dev/null 2>&1 &
  echo "started in background (pid $!) — open http://127.0.0.1:7878 (or your configured host/port)"
  exit 0
fi

exec "$PY" app.py --no-browser "${ARGS[@]}"
