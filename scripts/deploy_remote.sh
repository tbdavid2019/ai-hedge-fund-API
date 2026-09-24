#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/ubuntu/ai-hedge-fund-API"
cd "$REPO_DIR"

if [[ "${AI_HEDGE_FUND_SKIP_GIT_PULL:-0}" != "1" ]]; then
  git pull --ff-only origin main
fi

docker compose up -d --build --no-deps ai-hedge-fund-api

for attempt in $(seq 1 60); do
  if curl --fail --silent --show-error --max-time 3 http://localhost:6000/api/health > /tmp/ai-hedge-fund-health.json; then
    break
  fi
  if [[ "$attempt" == "60" ]]; then
    echo "API health check did not recover after deployment" >&2
    exit 1
  fi
  sleep 2
done

python3 -c 'import json; data=json.load(open("/tmp/ai-hedge-fund-health.json")); assert data.get("status") == "healthy", data; print(data)'

response="$(curl --silent --show-error --max-time 10 -w $'\n%{http_code}' \
  -X POST http://localhost:6000/api/backtest/grid \
  -H 'Content-Type: application/json' \
  -d '{"runId":"ci-smoke-test","tickers":[],"startDate":"2026-01-01","endDate":"2026-01-03"}')"
status="${response##*$'\n'}"
body="${response%$'\n'*}"
[[ "$status" == "400" ]]
printf '%s' "$body" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert "tickers" in data.get("error", ""), data; print(data)'
