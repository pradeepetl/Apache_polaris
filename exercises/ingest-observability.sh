#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Observability Ingestion Script
#
# Fetches Jaeger traces + Polaris container logs and loads them
# into Iceberg tables under the "observability" namespace.
#
# Usage:  bash exercises/ingest-observability.sh
# ============================================================

POLARIS="${POLARIS_URL:-http://localhost:8181}"
JAEGER="${JAEGER_URL:-http://localhost:16686}"
TRINO="${TRINO_URL:-https://localhost:8443}"
CATALOG="polaris_warehouse"
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

echo "=== Observability → Iceberg Ingestion ==="
echo ""

# ─── Helper: Polaris OAuth token ──────────────────────────

get_token() {
  curl -s -X POST "$POLARIS/api/catalog/v1/oauth/tokens" \
    -d "grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

polaris_api() {
  local method=$1 path=$2
  shift 2
  curl -s -X "$method" "$POLARIS/api/catalog/v1/$CATALOG$path" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    "$@"
}

# ─── Helper: Execute SQL on Trino via REST API ───────────
# Accepts SQL as $1 (short statements) or reads from file $2

trino_sql() {
  local sql_file="$TMPDIR/sql_input.sql"
  if [ -n "${2:-}" ] && [ -f "${2:-}" ]; then
    sql_file="$2"
  else
    printf '%s' "$1" > "$sql_file"
  fi

  local next_uri
  next_uri=$(curl -sk -X POST "$TRINO/v1/statement" \
    -u admin:admin123 \
    -H "X-Trino-User: admin" \
    -H "X-Trino-Catalog: iceberg" \
    -H "X-Trino-Schema: observability" \
    --data-binary "@$sql_file" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('nextUri','DONE')); e=d.get('error'); e and print('ERROR:',e.get('message',''),file=sys.stderr)")

  if [ "$next_uri" = "DONE" ]; then
    return 0
  fi

  while true; do
    local resp
    resp=$(curl -sk "$next_uri" -u admin:admin123 -H "X-Trino-User: admin")
    local state
    state=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('stats',{}).get('state','UNKNOWN'))")

    case "$state" in
      FINISHED)
        return 0
        ;;
      FAILED)
        echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print('SQL ERROR:', d.get('error',{}).get('message','unknown'))" >&2
        return 1
        ;;
      *)
        next_uri=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('nextUri','DONE'))")
        if [ "$next_uri" = "DONE" ]; then
          return 0
        fi
        sleep 0.3
        ;;
    esac
  done
}

trino_sql_file() {
  local sql_file="$1"
  trino_sql "" "$sql_file"
}

drop_table() {
  local table=$1
  curl -s -X DELETE "$POLARIS/api/catalog/v1/$CATALOG/namespaces/observability/tables/$table" \
    -H "Authorization: Bearer $TOKEN" > /dev/null 2>&1 || true
}


# ─── Step 1: Create observability namespace ───────────────

echo "1. Setting up namespace..."
TOKEN=$(get_token)

polaris_api POST /namespaces \
  -d '{"namespace": ["observability"]}' 2>/dev/null \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
ns = d.get('namespace')
if ns:
    print('   Created namespace: observability')
else:
    msg = d.get('error',{}).get('message','')
    if 'AlreadyExists' in msg or 'already exists' in msg.lower():
        print('   Namespace observability already exists')
    else:
        print('   Response:', json.dumps(d)[:200])
" 2>/dev/null || echo "   Namespace observability already exists"

echo "   Creating Trino schema..."
trino_sql "CREATE SCHEMA IF NOT EXISTS iceberg.observability" > /dev/null 2>&1 || true
echo "   Done."
echo ""


# ─── Step 2: Fetch and load traces ───────────────────────

echo "2. Fetching traces from Jaeger..."

curl -s "$JAEGER/api/traces?service=polaris-server&limit=500" > "$TMPDIR/traces.json"
TRACE_COUNT=$(python3 -c "
import json
with open('$TMPDIR/traces.json') as f:
    d = json.load(f)
print(sum(len(t['spans']) for t in d.get('data',[])))
")
echo "   Found $TRACE_COUNT spans"

if [ "$TRACE_COUNT" -gt 0 ]; then
  echo "   Generating SQL..."

  python3 -c "
import json
from datetime import datetime, timezone

with open('$TMPDIR/traces.json') as f:
    data = json.load(f)

def esc(v):
    return str(v).replace(chr(39), chr(39)+chr(39))

rows = []
for trace in data.get('data', []):
    svc_name = ''
    svc_version = ''
    procs = trace.get('processes', {})
    for pid, pinfo in procs.items():
        svc_name = pinfo.get('serviceName', '')
        for t in pinfo.get('tags', []):
            if t['key'] == 'service.version':
                svc_version = str(t['value'])
        break

    for span in trace.get('spans', []):
        tags = {t['key']: t['value'] for t in span.get('tags', [])}

        start_us = span['startTime']
        dt = datetime.fromtimestamp(start_us / 1_000_000, tz=timezone.utc)
        ts = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        row = (
            esc(span['traceID']),
            esc(span['spanID']),
            esc(span['operationName']),
            ts,
            span['duration'],
            esc(tags.get('http.request.method', '')),
            tags.get('http.response.status_code', 0),
            esc(tags.get('url.path', '')),
            esc(tags.get('client.address', '')),
            esc(tags.get('polaris.realm.id', '')),
            esc(tags.get('polaris.request.id', '')),
            esc(svc_name),
            esc(svc_version),
        )

        rows.append(
            \"('{0}', '{1}', '{2}', TIMESTAMP '{3}', {4}, '{5}', {6}, '{7}', '{8}', '{9}', '{10}', '{11}', '{12}')\"
            .format(*row)
        )

sql = 'CREATE TABLE iceberg.observability.traces AS\n'
sql += 'SELECT * FROM (VALUES\n'
sql += ',\n'.join(rows)
sql += '\n) AS t(trace_id, span_id, operation_name, start_time, duration_us, http_method, http_status, url_path, client_address, realm_id, request_id, service_name, service_version)'

with open('$TMPDIR/traces.sql', 'w') as f:
    f.write(sql)
print(f'   SQL generated: {len(sql)//1024} KB, {len(rows)} rows')
"

  echo "   Dropping old traces table..."
  drop_table traces
  sleep 1

  echo "   Creating traces table ($TRACE_COUNT rows)..."
  trino_sql_file "$TMPDIR/traces.sql"
  echo "   Done."
else
  echo "   No traces found — skipping."
fi
echo ""


# ─── Step 3: Fetch and load logs ─────────────────────────

echo "3. Fetching logs from Polaris container..."

docker logs polaris --tail 500 2>&1 > "$TMPDIR/logs.raw"
LOG_COUNT=$(wc -l < "$TMPDIR/logs.raw" | tr -d ' ')
echo "   Got $LOG_COUNT raw log lines"

echo "   Parsing logs..."

python3 -c "
import re

pattern = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+'
    r'(\w+)\s+'
    r'\[([^\]]*)\]\s+'
    r'\[([^\]]*)\]\s+'
    r'\[([^\]]*)\]\s+'
    r'\(([^)]*)\)\s+'
    r'(.*)'
)

http_pattern = re.compile(
    r'(\S+)\s+-\s+-\s+\[[^\]]+\]\s+\"(\w+)\s+(\S+)\s+\S+\"\s+(\d+)\s+(\d+)'
)

def esc(v):
    return str(v).replace(chr(39), chr(39)+chr(39))

rows = []
with open('$TMPDIR/logs.raw') as f:
    for line in f:
        line = line.rstrip()
        m = pattern.match(line)
        if not m:
            continue

        ts_raw, level, logger, ctx1, ctx2, thread, message = m.groups()

        ts = ts_raw.replace(',', '.')

        ctx1_parts = [x.strip() for x in ctx1.split(',')]
        request_id = ctx1_parts[0] if len(ctx1_parts) > 0 else ''
        realm_id = ctx1_parts[1] if len(ctx1_parts) > 1 else ''

        ctx2_parts = [x.strip() for x in ctx2.split(',')]
        trace_id = ctx2_parts[0] if len(ctx2_parts) > 0 else ''
        span_id = ctx2_parts[2] if len(ctx2_parts) > 2 else ''

        client_ip = ''
        http_method = ''
        http_path = ''
        http_status = 0
        response_size = 0

        hm = http_pattern.search(message)
        if hm:
            client_ip = hm.group(1)
            http_method = hm.group(2)
            http_path = hm.group(3)
            http_status = int(hm.group(4))
            response_size = int(hm.group(5))

        row = (
            ts,
            esc(level),
            esc(logger),
            esc(request_id),
            esc(realm_id),
            esc(trace_id),
            esc(span_id),
            esc(thread),
            esc(client_ip),
            esc(http_method),
            esc(http_path),
            http_status,
            response_size,
        )

        rows.append(
            \"(TIMESTAMP '{0}', '{1}', '{2}', '{3}', '{4}', '{5}', '{6}', '{7}', '{8}', '{9}', '{10}', {11}, {12})\"
            .format(*row)
        )

if not rows:
    with open('$TMPDIR/logs.sql', 'w') as f:
        f.write('SELECT 1 WHERE false')
    print('   0 entries parsed')
else:
    sql = 'CREATE TABLE iceberg.observability.logs AS\n'
    sql += 'SELECT * FROM (VALUES\n'
    sql += ',\n'.join(rows)
    sql += '\n) AS t(log_timestamp, log_level, logger, request_id, realm_id, trace_id, span_id, thread, client_ip, http_method, http_path, http_status, response_size)'
    with open('$TMPDIR/logs.sql', 'w') as f:
        f.write(sql)
    print(f'   {len(rows)} entries parsed ({len(sql)//1024} KB SQL)')
"

PARSED_COUNT=$(python3 -c "
with open('$TMPDIR/logs.sql') as f:
    sql = f.read()
if 'WHERE false' in sql:
    print('0')
else:
    print(sql.count('(TIMESTAMP'))
")

if [ "$PARSED_COUNT" -gt 0 ]; then
  echo "   Dropping old logs table..."
  drop_table logs
  sleep 1

  echo "   Creating logs table ($PARSED_COUNT rows)..."
  trino_sql_file "$TMPDIR/logs.sql"
  echo "   Done."
else
  echo "   No parseable log entries — skipping."
fi
echo ""


# ─── Step 4: Summary ─────────────────────────────────────

echo "=== Ingestion Complete ==="
echo ""
echo "Tables created:"
echo "  iceberg.observability.traces  ($TRACE_COUNT spans)"
echo "  iceberg.observability.logs    ($PARSED_COUNT entries)"
echo ""
echo "=== Sample Queries ==="
echo ""
echo "-- Top 10 slowest API calls"
echo "SELECT operation_name, duration_us, url_path, http_status"
echo "FROM iceberg.observability.traces"
echo "ORDER BY duration_us DESC LIMIT 10;"
echo ""
echo "-- Error rate by endpoint"
echo "SELECT url_path, http_status, COUNT(*) AS cnt"
echo "FROM iceberg.observability.traces"
echo "GROUP BY url_path, http_status"
echo "ORDER BY cnt DESC;"
echo ""
echo "-- Log entries by HTTP status"
echo "SELECT http_path, http_status, COUNT(*) AS cnt"
echo "FROM iceberg.observability.logs"
echo "WHERE http_status > 0"
echo "GROUP BY http_path, http_status"
echo "ORDER BY cnt DESC;"
echo ""
echo "-- Correlate traces with logs (join on trace_id)"
echo "SELECT t.trace_id, t.operation_name, t.duration_us,"
echo "       l.http_path, l.log_timestamp"
echo "FROM iceberg.observability.traces t"
echo "JOIN iceberg.observability.logs l ON t.trace_id = l.trace_id"
echo "ORDER BY t.duration_us DESC LIMIT 10;"
