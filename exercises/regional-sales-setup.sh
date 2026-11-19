#!/usr/bin/env bash
set -euo pipefail

POLARIS="${POLARIS_URL:-http://localhost:8181}"
CATALOG="polaris_warehouse"

echo "=== Regional Sales - Namespace Setup ==="
echo ""

# Get token
TOKEN=$(curl -s -X POST "$POLARIS/api/catalog/v1/oauth/tokens" \
  -d "grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

api() {
  local method=$1 path=$2
  shift 2
  curl -s -X "$method" "$POLARIS/api/catalog/v1/$CATALOG$path" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    "$@"
}

# Create region namespaces
for region in north_america europe asia_pacific; do
  echo "Creating region: $region"
  api POST /namespaces -d "{\"namespace\": [\"$region\"]}" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('  →', d.get('namespace', d.get('error',{}).get('message','ok')))" 2>/dev/null || echo "  → already exists"
done

echo ""

# Create country sub-namespaces
declare -A COUNTRIES=(
  ["north_america"]="usa canada"
  ["europe"]="uk germany"
  ["asia_pacific"]="japan india"
)

for region in north_america europe asia_pacific; do
  for country in ${COUNTRIES[$region]}; do
    echo "Creating country: $region.$country"
    api POST /namespaces -d "{\"namespace\": [\"$region\", \"$country\"]}" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('  →', d.get('namespace', d.get('error',{}).get('message','ok')))" 2>/dev/null || echo "  → already exists"
  done
done

echo ""
echo "Namespaces created. Now run the SQL in exercises/regional-sales.sql via Trino."
