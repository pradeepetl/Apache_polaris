#!/usr/bin/env bash
# Polaris Namespace Operations — end-to-end example
set -euo pipefail

POLARIS_HOST="${POLARIS_URL:-http://localhost:8181}"
CATALOG="polaris_warehouse"
REALM="POLARIS"

# ─── Helper ───────────────────────────────────────────────────────────
get_token() {
  curl -s -X POST "$POLARIS_HOST/api/catalog/v1/oauth/tokens" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

api() {
  local method=$1 path=$2; shift 2
  curl -s -X "$method" "$POLARIS_HOST/api/catalog/v1/$CATALOG$path" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Polaris-Realm: $REALM" \
    -H "Content-Type: application/json" \
    "$@"
}

mgmt() {
  local method=$1 path=$2; shift 2
  curl -s -X "$method" "$POLARIS_HOST/api/management/v1$path" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Polaris-Realm: $REALM" \
    -H "Content-Type: application/json" \
    "$@"
}

pp() { python3 -m json.tool 2>/dev/null || true; }

echo "============================================"
echo "  Polaris Namespaces — Hands-on Example"
echo "============================================"
echo ""

TOKEN=$(get_token)
echo "✓ Authenticated"
echo ""

# ─── 1. List existing namespaces ──────────────────────────────────────
echo "─── 1. List existing namespaces ───"
api GET /namespaces | pp
echo ""

# ─── 2. Create a top-level namespace ──────────────────────────────────
echo "─── 2. Create namespace: 'sales' ───"
api POST /namespaces -d '{
  "namespace": ["sales"],
  "properties": {
    "owner": "data-team",
    "description": "Sales department data",
    "environment": "dev"
  }
}' | pp
echo ""

# ─── 3. Create a nested namespace (multi-level) ──────────────────────
echo "─── 3. Create nested namespace: 'sales.regional' ───"
api POST /namespaces -d '{
  "namespace": ["sales", "regional"],
  "properties": {
    "owner": "sales-analytics",
    "description": "Regional sales breakdowns"
  }
}' | pp
echo ""

# ─── 4. Create another top-level namespace ────────────────────────────
echo "─── 4. Create namespace: 'hr' ───"
api POST /namespaces -d '{
  "namespace": ["hr"],
  "properties": {
    "owner": "hr-team",
    "description": "Human resources data"
  }
}' | pp
echo ""

# ─── 5. List all namespaces (now shows 4) ────────────────────────────
echo "─── 5. List all namespaces ───"
api GET /namespaces | pp
echo ""

# ─── 6. List child namespaces under 'sales' ──────────────────────────
echo "─── 6. List child namespaces under 'sales' ───"
api GET "/namespaces?parent=sales" | pp
echo ""

# ─── 7. Get namespace metadata ───────────────────────────────────────
echo "─── 7. Get metadata for 'sales' ───"
api GET /namespaces/sales | pp
echo ""

# ─── 8. Update namespace properties ──────────────────────────────────
echo "─── 8. Update 'sales' properties (add 'sla' and 'team-slack') ───"
api POST /namespaces/sales/properties -d '{
  "updates": {
    "sla": "99.9%",
    "team-slack": "#sales-data"
  },
  "removals": []
}' | pp
echo ""

echo "─── Verify updated properties ───"
api GET /namespaces/sales | pp
echo ""

# ─── 9. Create a table inside 'sales' namespace ──────────────────────
echo "─── 9. Create table 'sales.orders' ───"
api POST /namespaces/sales/tables -d '{
  "name": "orders",
  "schema": {
    "type": "struct",
    "fields": [
      {"id": 1, "name": "order_id",    "type": "long",      "required": true},
      {"id": 2, "name": "customer_id",  "type": "long",      "required": true},
      {"id": 3, "name": "product",      "type": "string",    "required": true},
      {"id": 4, "name": "amount",       "type": "double",    "required": true},
      {"id": 5, "name": "order_date",   "type": "date",      "required": true},
      {"id": 6, "name": "region",       "type": "string",    "required": false}
    ]
  },
  "properties": {
    "write.format.default": "parquet"
  }
}' | pp
echo ""

# ─── 10. Create a table inside nested namespace ──────────────────────
echo "─── 10. Create table 'sales.regional.metrics' ───"
# Nested namespaces use %1F (unit separator) encoding in the URL
api POST "/namespaces/sales%1Fregional/tables" -d '{
  "name": "metrics",
  "schema": {
    "type": "struct",
    "fields": [
      {"id": 1, "name": "region",       "type": "string",    "required": true},
      {"id": 2, "name": "quarter",      "type": "string",    "required": true},
      {"id": 3, "name": "revenue",      "type": "double",    "required": true},
      {"id": 4, "name": "units_sold",   "type": "long",      "required": true}
    ]
  }
}' | pp
echo ""

# ─── 11. List tables in each namespace ────────────────────────────────
echo "─── 11. List tables per namespace ───"
echo ""
echo "  earthquakes:"
api GET /namespaces/earthquakes/tables | pp
echo ""
echo "  sales:"
api GET /namespaces/sales/tables | pp
echo ""
echo "  sales.regional:"
api GET "/namespaces/sales%1Fregional/tables" | pp
echo ""
echo "  hr (empty):"
api GET /namespaces/hr/tables | pp
echo ""

# ─── 12. Query via Trino ─────────────────────────────────────────────
echo "─── 12. Verify namespaces visible in Trino ───"
echo "(requires Trino container running)"
echo ""
echo "  SHOW SCHEMAS:"
docker exec trino trino --user admin --password --execute \
  "SHOW SCHEMAS FROM iceberg" 2>/dev/null <<< "admin123" || echo "  (Trino not available — skip)"
echo ""

# ─── 13. Cleanup: drop the example namespaces ────────────────────────
echo "─── 13. Cleanup ───"

echo "  Dropping table sales.regional.metrics..."
api DELETE "/namespaces/sales%1Fregional/tables/metrics" | pp

echo "  Dropping namespace sales.regional..."
api DELETE "/namespaces/sales%1Fregional" | pp

echo "  Dropping table sales.orders..."
api DELETE "/namespaces/sales/tables/orders" | pp

echo "  Dropping namespace sales..."
api DELETE /namespaces/sales | pp

echo "  Dropping namespace hr..."
api DELETE /namespaces/hr | pp
echo ""

echo "─── Final state ───"
api GET /namespaces | pp
echo ""

echo "============================================"
echo "  Done! Original state restored."
echo "============================================"
