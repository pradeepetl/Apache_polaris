#!/bin/sh
set -e

POLARIS_HOST="http://polaris:8181"
CLIENT_ID="root"
CLIENT_SECRET="s3cr3t"
CATALOG_NAME="polaris_warehouse"
REALM="POLARIS"

echo "Waiting for Polaris to be ready..."
until curl -sf "http://polaris:8182/q/health" > /dev/null 2>&1; do
  sleep 2
done
echo "Polaris is ready"

echo "Obtaining root access token..."
TOKEN_RESPONSE=$(curl -s -X POST "$POLARIS_HOST/api/catalog/v1/oauth/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&scope=PRINCIPAL_ROLE:ALL")

TOKEN=$(echo "$TOKEN_RESPONSE" | sed 's/.*"access_token":"\([^"]*\)".*/\1/')
if [ -z "$TOKEN" ] || [ "$TOKEN" = "$TOKEN_RESPONSE" ]; then
  # Polaris state persists in Postgres, so a rotated root secret means setup already ran.
  echo "Could not log in as ${CLIENT_ID} with the bootstrap secret (rotated?). Response: $TOKEN_RESPONSE"
  echo "Skipping setup; existing Polaris state is kept."
  exit 0
fi
echo "Got token"

echo "Creating catalog '${CATALOG_NAME}'..."
curl -s -X POST "$POLARIS_HOST/api/management/v1/catalogs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Polaris-Realm: $REALM" \
  -d '{
    "catalog": {
      "name": "'"${CATALOG_NAME}"'",
      "type": "INTERNAL",
      "readOnly": false,
      "properties": {
        "default-base-location": "s3://warehouse/polaris_warehouse"
      },
      "storageConfigInfo": {
        "storageType": "S3",
        "allowedLocations": ["s3://warehouse/polaris_warehouse/"],
        "roleArn": "arn:aws:iam::000000000000:role/polaris-s3-role",
        "endpoint": "http://localstack:4566",
        "pathStyleAccess": true,
        "region": "us-east-1"
      }
    }
  }'
echo ""
echo "Catalog created"

echo "Creating principal role 'trino_role'..."
curl -s -X POST "$POLARIS_HOST/api/management/v1/principal-roles" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Polaris-Realm: $REALM" \
  -H "Content-Type: application/json" \
  -d '{"principalRole": {"name": "trino_role", "properties": {}}}'
echo ""

echo "Creating catalog role 'trino_catalog_role'..."
curl -s -X POST "$POLARIS_HOST/api/management/v1/catalogs/${CATALOG_NAME}/catalog-roles" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Polaris-Realm: $REALM" \
  -H "Content-Type: application/json" \
  -d '{"catalogRole": {"name": "trino_catalog_role", "properties": {}}}'
echo ""

echo "Assigning principal role to root..."
curl -s -X PUT "$POLARIS_HOST/api/management/v1/principals/root/principal-roles" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Polaris-Realm: $REALM" \
  -H "Content-Type: application/json" \
  -d '{"principalRole": {"name": "trino_role"}}'
echo ""

echo "Assigning catalog role to principal role..."
curl -s -X PUT "$POLARIS_HOST/api/management/v1/principal-roles/trino_role/catalog-roles/${CATALOG_NAME}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Polaris-Realm: $REALM" \
  -H "Content-Type: application/json" \
  -d '{"catalogRole": {"name": "trino_catalog_role"}}'
echo ""

echo "Granting CATALOG_MANAGE_CONTENT privilege..."
curl -s -X PUT "$POLARIS_HOST/api/management/v1/catalogs/${CATALOG_NAME}/catalog-roles/trino_catalog_role/grants" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Polaris-Realm: $REALM" \
  -H "Content-Type: application/json" \
  -d '{"type": "catalog", "privilege": "CATALOG_MANAGE_CONTENT"}'
echo ""

echo "Creating namespace 'earthquakes'..."
curl -s -X POST "$POLARIS_HOST/api/catalog/v1/${CATALOG_NAME}/namespaces" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Polaris-Realm: $REALM" \
  -H "Content-Type: application/json" \
  -d '{"namespace": ["earthquakes"]}'
echo ""

echo "Polaris setup complete!"
