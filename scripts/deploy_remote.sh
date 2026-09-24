#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/ubuntu/ai-hedge-fund-API"
cd "$REPO_DIR"

if [[ "${AI_HEDGE_FUND_SKIP_GIT_PULL:-0}" != "1" ]]; then
  git pull --ff-only origin main
fi

docker compose build ai-hedge-fund-api

mkdir -p "$REPO_DIR/instance"
if [[ ! -f "$REPO_DIR/instance/backtest_runs.sqlite3" ]] && docker inspect nice_jemison >/dev/null 2>&1; then
  legacy_db_path="$(docker exec nice_jemison python -c 'import os; print(os.path.abspath(os.getenv("BACKTEST_RUN_DB", "instance/backtest_runs.sqlite3")))')"
  if docker exec nice_jemison test -f "$legacy_db_path"; then
    docker stop --time 30 nice_jemison
    migration_dir="$(mktemp -d)"
    docker cp "nice_jemison:$legacy_db_path" "$migration_dir/source.sqlite3"
    docker cp "nice_jemison:$legacy_db_path-wal" "$migration_dir/source.sqlite3-wal" 2>/dev/null || true
    docker cp "nice_jemison:$legacy_db_path-shm" "$migration_dir/source.sqlite3-shm" 2>/dev/null || true
    python3 - "$migration_dir/source.sqlite3" "$REPO_DIR/instance/backtest_runs.sqlite3" <<'PY'
import sqlite3
import sys

source = sqlite3.connect(sys.argv[1])
target = sqlite3.connect(sys.argv[2])
source.backup(target)
target.close()
source.close()
PY
    rm -rf "$migration_dir"
    chown "$(id -u):$(id -g)" "$REPO_DIR/instance/backtest_runs.sqlite3"
    echo "Migrated the existing SQLite backtest run store to persistent host storage"
  fi
fi

if docker inspect nice_jemison >/dev/null 2>&1; then
  compose_service="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.service" }}' nice_jemison)"
  if [[ "$compose_service" != "ai-hedge-fund-api" ]]; then
    if [[ "$(docker inspect --format '{{.State.Running}}' nice_jemison)" == "true" ]]; then
      docker stop --time 30 nice_jemison
    fi
    legacy_name="nice_jemison_pre_compose_$(date +%Y%m%d%H%M%S)"
    docker rename nice_jemison "$legacy_name"
    echo "Preserved the previous unmanaged container as $legacy_name"
  fi
fi

docker compose up -d --no-build --no-deps ai-hedge-fund-api

database_path="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/instance"}}{{.Source}}{{end}}{{end}}' nice_jemison)"
[[ "$database_path" == "$REPO_DIR/instance" ]]
database_env="$(docker inspect --format '{{range .Config.Env}}{{if eq . "BACKTEST_RUN_DB=/app/instance/backtest_runs.sqlite3"}}{{.}}{{end}}{{end}}' nice_jemison)"
[[ -n "$database_env" ]]

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
  -d '{"runId":"ci-smoke-invalid-analyst","tickers":["MSFT"],"startDate":"2026-01-01","endDate":"2026-01-03","selectedAnalysts":["technicals"]}')"
status="${response##*$'\n'}"
body="${response%$'\n'*}"
[[ "$status" == "400" ]]
printf '%s' "$body" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert "technicals" in data.get("error", ""), data; print(data)'
