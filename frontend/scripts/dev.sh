#!/usr/bin/env bash
# Launch the report-aggregator API and the Next.js dev server together.
#
# The Python backend is the parent directory of this frontend/ folder
# (i.e. the monorepo root). Override with REPORT_AGGREGATOR_DIR if needed.
set -euo pipefail

UI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="${REPORT_AGGREGATOR_DIR:-$(cd "$UI_DIR/.." && pwd)}"

echo "API dir: $API_DIR"
echo "UI dir:  $UI_DIR"

cleanup() {
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT

( cd "$API_DIR" && python3 -m report_aggregator.api ) &
API_PID=$!

( cd "$UI_DIR" && npm run dev )
