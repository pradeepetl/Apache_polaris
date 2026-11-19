#!/usr/bin/env bash
# Load the global sales dataset into the global_sales catalog via Trino.
# Usage: bash exercises/global-sales-load.sh [--setup] [--reset]
#   --setup  run global-sales-setup.sh first (creates the Polaris catalog + namespaces)
#   --reset  drop existing global_sales tables/namespaces before loading
set -euo pipefail

cd "$(dirname "$0")"

TRINO_CONTAINER="${TRINO_CONTAINER:-trino}"
TRINO_USER="${TRINO_USER:-admin}"
TRINO_PASSWORD="${TRINO_PASSWORD:-admin123}"
TRINO_CATALOG="global_sales"
SQL_FILE="global-sales.sql"
POLARIS_URL="${POLARIS_URL:-http://localhost:8181}"
CLIENT_ID="${CLIENT_ID:-root}"
CLIENT_SECRET="${CLIENT_SECRET:-s3cr3t}"

RUN_SETUP=false
RESET=false
for arg in "$@"; do
  case "$arg" in
    --setup) RUN_SETUP=true ;;
    --reset) RESET=true ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

trino_exec() {
  docker exec -i -e TRINO_PASSWORD="$TRINO_PASSWORD" "$TRINO_CONTAINER" \
    trino --server https://localhost:8443 --user "$TRINO_USER" --password --insecure \
    --output-format ALIGNED "$@"
}

has_catalog() {
  local catalogs
  catalogs=$(trino_exec --execute "SHOW CATALOGS" 2>/dev/null) || return 1
  grep -qw "$TRINO_CATALOG" <<<"$catalogs"
}

wait_for_trino() {
  for _ in $(seq 1 60); do
    trino_exec --execute "SELECT 1" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

# Drops a table entry in Polaris without purging files; prints the HTTP code.
polaris_drop_table() {
  local namespace=$1 table=$2 token
  token=$(curl -s -X POST "$POLARIS_URL/api/catalog/v1/oauth/tokens" \
    -d "grant_type=client_credentials&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&scope=PRINCIPAL_ROLE:ALL" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
  # Nested namespace levels are separated by the 0x1F unit separator in REST paths.
  curl -s -o /dev/null -w '%{http_code}' -X DELETE \
    "$POLARIS_URL/api/catalog/v1/$TRINO_CATALOG/namespaces/${namespace//./%1F}/tables/$table" \
    -H "Authorization: Bearer $token"
}

echo "=== Global Sales - Load via Trino ==="

if $RUN_SETUP; then
  echo ""
  bash ./global-sales-setup.sh
fi

echo ""
if ! docker ps --format '{{.Names}}' | grep -qx "$TRINO_CONTAINER"; then
  echo "Trino container '$TRINO_CONTAINER' is not running." >&2
  exit 1
fi

if ! trino_exec --execute "SELECT 1" >/dev/null 2>&1; then
  echo "Cannot connect to Trino as '$TRINO_USER' (still starting, or wrong password)." >&2
  exit 1
fi
echo "✓ Connected to Trino as $TRINO_USER"

# Trino loads catalog files only at startup, so a newly added global_sales.properties needs a restart.
if ! has_catalog; then
  echo "Trino has no '$TRINO_CATALOG' catalog yet (etc/catalog/$TRINO_CATALOG.properties) — restarting Trino..."
  docker restart "$TRINO_CONTAINER" >/dev/null
  if ! wait_for_trino; then
    echo "Trino did not come back within 2 minutes." >&2
    exit 1
  fi
  if ! has_catalog; then
    echo "Catalog '$TRINO_CATALOG' still missing — check etc/catalog/$TRINO_CATALOG.properties." >&2
    exit 1
  fi
  echo "✓ Trino restarted with catalog $TRINO_CATALOG"
fi

if ! trino_exec --execute "SHOW SCHEMAS FROM $TRINO_CATALOG" >/dev/null 2>&1; then
  echo "Polaris catalog '$TRINO_CATALOG' not reachable from Trino — run with --setup first." >&2
  exit 1
fi

if $RESET; then
  echo ""
  echo "─── Reset: dropping existing global_sales tables and namespaces ───"
  TABLE_RE='^DROP TABLE IF EXISTS global_sales\."([^"]+)"\.([a-z_]+)$'
  sed -n '/^-- CLEANUP/,$p' "$SQL_FILE" | sed -n 's/^-- \(DROP .*\);$/\1/p' | while IFS= read -r stmt; do
    trino_exec --execute "$stmt" </dev/null >/dev/null 2>&1 && continue
    # Trino cannot drop a table whose metadata file is gone from S3 (e.g. LocalStack lost its data); drop the Polaris entry directly.
    if [[ $stmt =~ $TABLE_RE ]]; then
      code=$(polaris_drop_table "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}") || true
      case "$code" in
        204|404) echo "  • ${BASH_REMATCH[1]}.${BASH_REMATCH[2]}: S3 files missing, removed from Polaris" ;;
        *)       echo "  ✗ ${BASH_REMATCH[1]}.${BASH_REMATCH[2]}: drop failed (Polaris HTTP $code)" ;;
      esac
    else
      echo "  ✗ $stmt failed"
    fi
  done
fi

echo ""
echo "─── Loading $SQL_FILE ───"
# Strip line comments so the commented-out sample queries and cleanup are not executed.
sed -e 's/--.*$//' "$SQL_FILE" | trino_exec
echo "✓ Load complete"

echo ""
echo "─── Verify: schemas ───"
trino_exec --execute "SHOW SCHEMAS FROM $TRINO_CATALOG"

echo ""
echo "─── Verify: total sales by country (local currency) ───"
trino_exec --execute "
SELECT 'UAE' AS country, count(*) AS orders, sum(amount) AS total FROM global_sales.\"middle_east.uae\".sales
UNION ALL SELECT 'Saudi Arabia', count(*), sum(amount) FROM global_sales.\"middle_east.saudi_arabia\".sales
UNION ALL SELECT 'South Africa', count(*), sum(amount) FROM global_sales.\"africa.south_africa\".sales
UNION ALL SELECT 'Nigeria',      count(*), sum(amount) FROM global_sales.\"africa.nigeria\".sales
UNION ALL SELECT 'Brazil',       count(*), sum(amount) FROM global_sales.\"latin_america.brazil\".sales
UNION ALL SELECT 'Mexico',       count(*), sum(amount) FROM global_sales.\"latin_america.mexico\".sales
UNION ALL SELECT 'Australia',    count(*), sum(amount) FROM global_sales.\"oceania.australia\".sales
UNION ALL SELECT 'New Zealand',  count(*), sum(amount) FROM global_sales.\"oceania.new_zealand\".sales
ORDER BY country"

echo ""
echo "Done. Try the sample queries at the bottom of exercises/$SQL_FILE."
