#!/usr/bin/env bash
# Load the regional sales dataset into Trino.
# Usage: bash exercises/regional-sales-load.sh [--setup] [--reset]
#   --setup  run regional-sales-setup.sh first (creates namespaces via Polaris API)
#   --reset  drop existing regional tables/namespaces before loading
set -euo pipefail

cd "$(dirname "$0")"

TRINO_CONTAINER="${TRINO_CONTAINER:-trino}"
TRINO_USER="${TRINO_USER:-admin}"
TRINO_PASSWORD="${TRINO_PASSWORD:-admin123}"
SQL_FILE="regional-sales.sql"

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

echo "=== Regional Sales - Load via Trino ==="
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

if ! trino_exec --execute "SHOW SCHEMAS FROM iceberg" >/dev/null 2>&1; then
  echo "Iceberg catalog not reachable from Trino — is Polaris up and polaris_warehouse created?" >&2
  exit 1
fi

if $RUN_SETUP; then
  echo ""
  bash ./regional-sales-setup.sh
fi

if $RESET; then
  echo ""
  echo "─── Reset: dropping existing regional tables and namespaces ───"
  # The cleanup block at the end of the SQL file is commented out; uncomment and run it.
  sed -n '/^-- CLEANUP/,$p' "$SQL_FILE" | sed -n 's/^-- \(DROP .*\)$/\1/p' | trino_exec || true
fi

echo ""
echo "─── Loading $SQL_FILE ───"
# Strip line comments so the commented-out sample queries and cleanup are not executed.
sed -e 's/--.*$//' "$SQL_FILE" | trino_exec
echo "✓ Load complete"

echo ""
echo "─── Verify: schemas ───"
trino_exec --execute "SHOW SCHEMAS FROM iceberg"

echo ""
echo "─── Verify: total sales by country ───"
trino_exec --execute "
SELECT 'USA' AS country, count(*) AS orders, sum(amount) AS total FROM iceberg.\"north_america.usa\".sales
UNION ALL SELECT 'Canada',  count(*), sum(amount) FROM iceberg.\"north_america.canada\".sales
UNION ALL SELECT 'UK',      count(*), sum(amount) FROM iceberg.\"europe.uk\".sales
UNION ALL SELECT 'Germany', count(*), sum(amount) FROM iceberg.\"europe.germany\".sales
UNION ALL SELECT 'Japan',   count(*), sum(amount) FROM iceberg.\"asia_pacific.japan\".sales
UNION ALL SELECT 'India',   count(*), sum(amount) FROM iceberg.\"asia_pacific.india\".sales
ORDER BY country"

echo ""
echo "Done. Try the sample queries at the bottom of exercises/$SQL_FILE."
