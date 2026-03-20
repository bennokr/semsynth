#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8123}"
HOST="http://localhost:${PORT}/output/"

export ROOT_DIR
export PORT

server_pid=""
rodney_started=false
server_running=false

cleanup() {
  if $rodney_started; then
    uvx rodney stop --local >/dev/null 2>&1 || true
  fi
  if [[ -n "${server_pid}" ]]; then
    kill "${server_pid}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

python3 - <<'PY' &
import http.server
import mimetypes
import pathlib
import socketserver
import sys

port = int(__import__("os").environ.get("PORT", "8123"))
root = pathlib.Path(__import__("os").environ["ROOT_DIR"])

class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".json": "application/ld+json",
        ".jsonld": "application/ld+json",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(root), **kwargs)

class ReuseTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

try:
    with ReuseTCPServer(("", port), Handler) as httpd:
        httpd.serve_forever()
except OSError as exc:
    sys.exit(2)
PY
server_pid=$!
sleep 1
if ! kill -0 "${server_pid}" >/dev/null 2>&1; then
  echo "Reusing existing server on port ${PORT}"
  server_pid=""
  server_running=true
fi

uvx rodney stop --local >/dev/null 2>&1 || true
uvx rodney start --local
rodney_started=true

uvx rodney open "${HOST}"
uvx rodney clear-cache >/dev/null 2>&1 || true
uvx rodney reload --hard
uvx rodney wait ".yasgui"

uvx rodney js "(async () => { while (!window.semsynthApp) { await new Promise((r) => setTimeout(r, 100)); } window.__runResults = null; window.semsynthApp.runAllTabs().then((r) => { window.__runResults = r; return r; }); return 'started'; })()"

RESULTS_JSON=""
for _ in {1..50}; do
  RESULTS_JSON="$(uvx rodney js "window.__runResults ? JSON.stringify(window.__runResults) : null")"
  if [[ "${RESULTS_JSON}" != "null" && -n "${RESULTS_JSON}" ]]; then
    break
  fi
  sleep 0.2
done

if [[ -z "${RESULTS_JSON}" || "${RESULTS_JSON}" == "null" ]]; then
  echo "Failed to collect SPARQL results from the page" >&2
  exit 1
fi

export RESULTS_JSON
export SHOW_RESULTS

python3 - <<'PY'
import json
import os

results = json.loads(os.environ["RESULTS_JSON"])
show_payload = os.environ.get("SHOW_RESULTS", "").lower() in {"1", "true", "yes"}
for entry in results:
    name = entry.get("name", "unknown")
    error = entry.get("error")
    row_count = entry.get("rowCount")
    payload = entry.get("payload")
    if error:
        print(f"{name}: ERROR {error}")
    else:
        print(f"{name}: {row_count} rows")
        if show_payload and payload:
            print(payload)
PY
