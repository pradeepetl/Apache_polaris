# Cheatsheet — Trino + Polaris Quick Reference

## Trino CLI

```bash
# Admin (full access)
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure

# Analyst (read-only)
docker exec -e TRINO_PASSWORD=analyst123 -it trino \
  trino --server https://localhost:8443 --user analyst --password --insecure

# One-off query
docker exec -e TRINO_PASSWORD=admin123 trino \
  trino --server https://localhost:8443 --user admin --password --insecure \
  --execute "SELECT count(*) FROM postgres.public.customers"
```

## Common Trino Queries

```sql
-- Navigation
SHOW CATALOGS;
SHOW SCHEMAS IN iceberg;
SHOW TABLES IN iceberg.shop;
DESCRIBE iceberg.shop.orders;

-- Postgres tables
SELECT * FROM postgres.public.customers LIMIT 10;
SELECT * FROM postgres.public.products LIMIT 10;

-- Iceberg tables
SELECT * FROM iceberg.shop.orders LIMIT 10;
SELECT * FROM iceberg.shop.order_items LIMIT 10;
SELECT * FROM iceberg.earthquakes.events ORDER BY magnitude DESC LIMIT 10;

-- Federation (Postgres + Iceberg JOIN)
SELECT c.name, c.country, o.order_id, o.total_amount
FROM iceberg.shop.orders o
JOIN postgres.public.customers c ON o.customer_id = c.customer_id;

-- Memory catalog (temporary tables)
CREATE SCHEMA IF NOT EXISTS memory.scratch;
CREATE TABLE memory.scratch.tmp AS SELECT 1 AS id;
```

## Polaris REST API (curl)

### Get Token

```bash
TOKEN=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
  -d 'grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Management API (`/api/management/v1`)

```bash
MGMT="http://localhost:8181/api/management/v1"
AUTH="-H 'Authorization: Bearer $TOKEN' -H 'Polaris-Realm: POLARIS'"

# Catalogs
curl -s "$MGMT/catalogs" -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: POLARIS"

# Principals
curl -s "$MGMT/principals" -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: POLARIS"

# Principal Roles
curl -s "$MGMT/principal-roles" -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: POLARIS"

# Catalog Roles for a catalog
curl -s "$MGMT/catalogs/polaris_warehouse/catalog-roles" \
  -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: POLARIS"

# Grants for a catalog role
curl -s "$MGMT/catalogs/polaris_warehouse/catalog-roles/ROLE_NAME/grants" \
  -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: POLARIS"

# Create principal role
curl -s -X POST "$MGMT/principal-roles" \
  -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: POLARIS" \
  -H "Content-Type: application/json" \
  -d '{"principalRole":{"name":"my_role","properties":{}}}'

# Add grant to catalog role
curl -s -X PUT "$MGMT/catalogs/polaris_warehouse/catalog-roles/ROLE_NAME/grants" \
  -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: POLARIS" \
  -H "Content-Type: application/json" \
  -d '{"type":"table","privilege":"TABLE_READ_DATA","namespace":["shop"],"tableName":"orders"}'
```

### Catalog API (`/api/catalog/v1`)

```bash
CAT="http://localhost:8181/api/catalog/v1"
WH="polaris_warehouse"

# List namespaces
curl -s "$CAT/$WH/namespaces" \
  -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: POLARIS"

# List tables in a namespace
curl -s "$CAT/$WH/namespaces/shop/tables" \
  -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: POLARIS"

# Load table metadata
curl -s "$CAT/$WH/namespaces/shop/tables/orders" \
  -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: POLARIS"

# Create namespace
curl -s -X POST "$CAT/$WH/namespaces" \
  -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: POLARIS" \
  -H "Content-Type: application/json" \
  -d '{"namespace":["my_namespace"],"properties":{}}'
```

## Polaris Admin UI

- URL: http://localhost:3000
- Login: Client ID = `root`, Secret = `s3cr3t`, Realm = `POLARIS`

| Tab | Purpose |
|-----|---------|
| Dashboard | Overview of catalogs, namespaces, tables, roles |
| Data Browser | Browse catalog > namespace > table, view schemas |
| Access Control | Create/manage roles and grants |
| Catalogs | Create/view catalog details |
| Role Graph | Visual mapping of principal roles to catalog roles |
| API Explorer | Interactive REST API client for all endpoints |

## Spark (Jupyter)

- URL: http://localhost:8888?token=spark123

```python
# Query
spark.sql("SELECT * FROM polaris.shop.orders").show()

# Create table
spark.sql("CREATE TABLE polaris.shop.my_table (id INT, data STRING)")

# Insert
spark.sql("INSERT INTO polaris.shop.my_table VALUES (1, 'hello')")
```

## dlt Pipeline

```bash
# Check logs
docker logs dlt-earthquakes

# Re-run (appends new data)
docker restart dlt-earthquakes

# Query results
docker exec -e TRINO_PASSWORD=admin123 trino \
  trino --server https://localhost:8443 --user admin --password --insecure \
  --execute "SELECT count(*) FROM iceberg.earthquakes.events"
```

## Polaris Grant Privileges

| Scope | Privileges |
|-------|-----------|
| Catalog | `CATALOG_MANAGE_CONTENT`, `CATALOG_MANAGE_ACCESS` |
| Namespace | `NAMESPACE_CREATE`, `NAMESPACE_DROP`, `NAMESPACE_LIST`, `TABLE_CREATE`, `TABLE_DROP`, `TABLE_LIST`, `VIEW_CREATE`, `VIEW_LIST` |
| Table | `TABLE_READ_DATA`, `TABLE_WRITE_DATA`, `TABLE_READ_PROPERTIES`, `TABLE_WRITE_PROPERTIES`, `TABLE_DROP` |

## Docker Lifecycle

```bash
docker compose up -d          # Start all services
docker compose down            # Stop (keeps data volumes)
docker compose down -v         # Stop + wipe all data
docker logs trino              # View Trino logs
docker restart dlt-earthquakes # Re-run earthquake ingestion
docker ps                      # Check running containers
```

## Service Ports

| Port | Service |
|------|---------|
| 8080 | Trino Web UI (no auth) |
| 8443 | Trino HTTPS/JDBC (password auth) |
| 5432 | PostgreSQL |
| 8181 | Polaris Catalog API |
| 8182 | Polaris Management/Health |
| 3000 | Polaris Admin UI |
| 8888 | Spark Jupyter |
| 4566 | LocalStack S3 |

## Users

| User | Password | Access |
|------|----------|--------|
| `admin` | `admin123` | Full read/write on all catalogs |
| `analyst` | `analyst123` | Read-only on postgres + iceberg |
