#!/usr/bin/env bash
# Create a second Polaris catalog (global_sales) with nested region.country namespaces.
# Usage: bash exercises/global-sales-setup.sh
#   Env overrides: POLARIS_URL, CATALOG, CLIENT_ID, CLIENT_SECRET
set -euo pipefail

POLARIS="${POLARIS_URL:-http://localhost:8181}"
CATALOG="${CATALOG:-global_sales}"
CLIENT_ID="${CLIENT_ID:-root}"
CLIENT_SECRET="${CLIENT_SECRET:-s3cr3t}"
# Must not overlap polaris_warehouse (s3://warehouse/polaris_warehouse/)
BASE_LOCATION="s3://warehouse/${CATALOG}"

# region:country country ...
REGIONS=(
  "middle_east:uae saudi_arabia"
  "africa:south_africa nigeria"
  "latin_america:brazil mexico"
  "oceania:australia new_zealand"
)

echo "=== Global Sales - Catalog & Namespace Setup ==="
echo "Polaris: $POLARIS   Catalog: $CATALOG"
echo ""

TOKEN=$(curl -s -X POST "$POLARIS/api/catalog/v1/oauth/tokens" \
  -d "grant_type=client_credentials&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&scope=PRINCIPAL_ROLE:ALL" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
if [ -z "$TOKEN" ]; then
  echo "Failed to get a token for '$CLIENT_ID' from $POLARIS" >&2
  exit 1
fi

# Prints "<http_code> <message>" for a request.
call() {
  local method=$1 url=$2 body=${3:-}
  local out code
  local args=(-s -w '\n%{http_code}' -X "$method" "$POLARIS$url"
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")
  [ -n "$body" ] && args+=(-d "$body")
  out=$(curl "${args[@]}")
  code=$(printf '%s' "$out" | tail -n1)
  printf '%s' "$out" | sed '$d' | python3 -c "
import sys, json
code = '$code'
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
msg = d.get('error', {}).get('message') if isinstance(d, dict) and 'error' in d else 'ok'
print(code, msg)
"
}

report() {
  local label=$1 result=$2
  local code=${result%% *} msg=${result#* }
  case "$code" in
    200|201|204) echo "  ✓ $label" ;;
    409)         echo "  • $label (already exists)" ;;
    *)           echo "  ✗ $label → HTTP $code: $msg"; FAILED=1 ;;
  esac
}
FAILED=0

ROLE="${CATALOG}_role"
CATALOG_BODY=$(cat <<JSON
{
  "catalog": {
    "name": "$CATALOG",
    "type": "INTERNAL",
    "readOnly": false,
    "properties": {
      "default-base-location": "$BASE_LOCATION",
      "polaris.config.drop-with-purge.enabled": "true"
    },
    "storageConfigInfo": {
      "storageType": "S3",
      "allowedLocations": ["$BASE_LOCATION/"],
      "roleArn": "arn:aws:iam::000000000000:role/polaris-s3-role",
      "endpoint": "http://localstack:4566",
      "pathStyleAccess": true,
      "region": "us-east-1"
    }
  }
}
JSON
)
ROLE_BODY='{"catalogRole": {"name": "'"$ROLE"'"}}'
GRANT_BODY='{"type": "catalog", "privilege": "CATALOG_MANAGE_CONTENT"}'

echo "─── Catalog ───"
report "catalog $CATALOG ($BASE_LOCATION)" "$(call POST /api/management/v1/catalogs "$CATALOG_BODY")"

# Lets Trino DROP TABLE work (Trino always drops with purge); also fixes catalogs created before this setting.
PURGE_BODY=$(curl -s "$POLARIS/api/management/v1/catalogs/$CATALOG" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
c = json.load(sys.stdin)
if c.get('properties', {}).get('polaris.config.drop-with-purge.enabled') != 'true':
    print(json.dumps({'currentEntityVersion': c['entityVersion'],
                      'properties': {**c.get('properties', {}), 'polaris.config.drop-with-purge.enabled': 'true'}}))
" 2>/dev/null || true)
if [ -n "$PURGE_BODY" ]; then
  report "enable drop-with-purge" "$(call PUT "/api/management/v1/catalogs/$CATALOG" "$PURGE_BODY")"
fi

echo ""
echo "─── Access: $ROLE (CATALOG_MANAGE_CONTENT) → principal role trino_role ───"
report "catalog role $ROLE" "$(call POST "/api/management/v1/catalogs/$CATALOG/catalog-roles" "$ROLE_BODY")"
report "grant CATALOG_MANAGE_CONTENT" "$(call PUT "/api/management/v1/catalogs/$CATALOG/catalog-roles/$ROLE/grants" "$GRANT_BODY")"
report "assign to trino_role" "$(call PUT "/api/management/v1/principal-roles/trino_role/catalog-roles/$CATALOG" "$ROLE_BODY")"

echo ""
echo "─── Namespaces ───"
for entry in "${REGIONS[@]}"; do
  region=${entry%%:*}
  ns_body='{"namespace": ["'"$region"'"]}'
  report "$region" "$(call POST "/api/catalog/v1/$CATALOG/namespaces" "$ns_body")"
  for country in ${entry#*:}; do
    ns_body='{"namespace": ["'"$region"'", "'"$country"'"]}'
    report "$region.$country" "$(call POST "/api/catalog/v1/$CATALOG/namespaces" "$ns_body")"
  done
done

echo ""
if [ "$FAILED" -ne 0 ]; then
  echo "Finished with errors (see ✗ above)." >&2
  exit 1
fi
echo "Done. Browse it in the admin UI (Data Browser → $CATALOG)."
