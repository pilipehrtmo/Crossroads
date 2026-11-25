#!/usr/bin/env bash
# Start a local test server for the QA scripts.   usage: qa/run_server.sh <port> <db>
#   VERIFY=1  require email confirmation (default 0)      DEMO=1  load the demo projects (default 0)
#   QA_PYTHON python to use (default: python3)           QA_PG_URL  Postgres URL without the db name
#                                                        (default postgresql+psycopg2://postgres@127.0.0.1:5433)
set -e
PORT=$1; DB=$2
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${QA_LOG_DIR:-/var/tmp/lt}"; mkdir -p "$LOG_DIR"
pkill -f "[u]vicorn app.main.*--port $PORT" || true; sleep 1
cd "$ROOT" && : > "$LOG_DIR/srv_$PORT.log"
(ADMIN_EMAILS=admin@audit.test BASE_URL=http://localhost:$PORT DB_URL="${QA_PG_URL:-postgresql+psycopg2://postgres@127.0.0.1:5433}/$DB" \
 MATCH_MODE=tags SECRET_KEY=audit-secret REQUIRE_EMAIL_VERIFY=${VERIFY:-0} KEEP_AWAKE=0 DEMO_DATA=${DEMO:-0} \
 LOCAL_STORAGE_DIR="$LOG_DIR/up_$PORT" PYTHONDONTWRITEBYTECODE=1 \
 nohup "${QA_PYTHON:-python3}" -m uvicorn app.main:app --port $PORT > "$LOG_DIR/srv_$PORT.log" 2>&1 &)
for i in $(seq 1 60); do sleep 1; curl -s --noproxy '*' -o /dev/null -w "%{http_code}" http://localhost:$PORT/healthz 2>/dev/null | grep -q 200 && break; done
echo "server $PORT up after ${i}s"
