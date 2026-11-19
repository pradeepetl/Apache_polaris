# Trino Lab Environment

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Trino (v483)                      │
│              Query Federation Engine                 │
│         HTTP :8080 (UI)  │  HTTPS :8443 (JDBC)      │
├──────────┬──────────┬──────────┬────────────────────┤
│ postgres │ iceberg  │  tpch    │  tpcds / memory    │
│ catalog  │ catalog  │  catalog │  catalogs          │
└────┬─────┴────┬─────┴──────────┴────────────────────┘
     │          │
     ▼          ▼
┌──────────┐ ┌──────────────┐  ┌──────────────┐
│PostgreSQL│ │Apache Polaris│  │ LocalStack   │
│  :5432   │ │ (REST Catalog│  │ (S3) :4566   │
│          │ │  :8181/:8182)│  │              │
│customers │ │              │──│ s3://warehouse│
│products  │ │ polaris_     │  │  └─shop/     │
│          │ │ warehouse    │  │  └─earthquakes│
│          │ │  ▲  ▲  ▲     │  │              │
└──────────┘ └──┼──┼──┼─────┘  └──────────────┘
                │  │  │
       ┌────────┘  │  └─────────┐
       ▼           ▼            ▼
┌────────────┐ ┌──────────┐ ┌────────────────┐
│   Trino    │ │   dlt    │ │ Spark+Jupyter  │
│ (queries)  │ │(ingest)  │ │ (notebooks)    │
│  :8443     │ │ USGS API │ │  :8888         │
└────────────┘ └──────────┘ └────────────────┘
```

## Services

| Service      | Port  | Purpose                                     |
|-------------|-------|---------------------------------------------|
| Trino       | 8080  | Web UI (no auth)                            |
| Trino       | 8443  | HTTPS endpoint for JDBC/CLI (password auth) |
| PostgreSQL  | 5432  | Relational data store                       |
| Polaris     | 8181  | Iceberg REST Catalog API                    |
| Polaris     | 8182  | Polaris Management API                      |
| Polaris Admin | 3000 | Web UI for managing Polaris                 |
| Spark+Jupyter | 8888 | PySpark notebooks (Iceberg via Polaris)     |
| dlt           | -    | API ingestion pipeline (USGS earthquakes)   |
| LocalStack  | 4566  | S3-compatible object storage                |

## Access Control

### Users & Credentials

| User      | Password      | Access                                          |
|-----------|---------------|-------------------------------------------------|
| `admin`   | `admin123`    | Full read/write on all 6 catalogs               |
| `analyst` | `analyst123`  | Read-only on `postgres` and `iceberg` catalogs   |

### Analyst Restrictions
- Cannot see `system`, `tpch`, `tpcds`, `memory` catalogs
- Cannot CREATE, INSERT, DELETE, or DROP — read-only
- Can SELECT from `postgres.public.*` and `iceberg.shop.*`

### Adding New Users
```bash
# Generate bcrypt password hash
htpasswd -nbBC 10 newuser password123

# Append to etc/password.db
# Then add rules in etc/rules.json (auto-refreshes every 5s, no restart needed)
```

## Catalogs & Data

| Catalog    | Source                | Tables                               |
|------------|-----------------------|--------------------------------------|
| `postgres` | PostgreSQL            | `public.customers` (20 rows), `public.products` (20 rows) |
| `iceberg`  | Polaris REST Catalog  | `shop.orders` (15 rows), `shop.order_items` (24 rows), `earthquakes.events` (dlt) |
| `tpch`     | In-memory generated   | TPC-H benchmark (tiny/sf1/sf100)     |
| `tpcds`    | In-memory generated   | TPC-DS benchmark                     |
| `memory`   | JVM heap              | Empty — create your own tables       |

**Note:** Iceberg data in LocalStack does NOT persist across `podman compose down`.
After a restart, re-run the Iceberg table creation and inserts from `sample-queries.sql` (section 2).
Polaris catalog metadata is also in-memory and resets on restart.

### Polaris Admin UI
Open http://localhost:3000 — manage Polaris catalogs, roles, and grants from a browser.

- **Client ID:** `root`
- **Client Secret:** `s3cr3t`
- **Realm:** `POLARIS`

Features: browse catalogs, create/list principal roles and catalog roles, assign roles, manage grants, browse namespaces and tables.

### Polaris REST API
```bash
# List catalogs
curl -s http://localhost:8181/api/management/v1/catalogs \
  -H "Authorization: Bearer $(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
    -d 'grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL' | sed 's/.*"access_token":"\([^"]*\)".*/\1/')" \
  -H "Polaris-Realm: POLARIS"

# Polaris health
curl http://localhost:8182/q/health
```

## Running Queries

### Interactive CLI
```bash
# As admin (full access)
podman exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure

# As analyst (read-only)
podman exec -e TRINO_PASSWORD=analyst123 -it trino \
  trino --server https://localhost:8443 --user analyst --password --insecure
```

### One-Off Query
```bash
podman exec -e TRINO_PASSWORD=admin123 trino \
  trino --server https://localhost:8443 --user admin --password --insecure \
  --execute "SELECT * FROM postgres.public.customers LIMIT 5"
```

### Web UI
Open http://localhost:8080 — shows running/completed queries (monitoring only, no auth).

### DBeaver / JDBC Connection
- **Host:** `localhost`
- **Port:** `8443`
- **SSL:** Enabled (accept self-signed certificate)
- **User:** `admin` or `analyst`
- **Password:** `admin123` or `analyst123`

### Spark + Jupyter Notebook
Spark/Jupyter and Marimo are on-demand to save memory (full command reference: [on-demand-services.md](on-demand-services.md)). Start them when needed:

```bash
docker compose --profile spark up -d     # Spark Jupyter (:8888)
docker compose --profile marimo up -d    # Marimo (:2718)
docker compose stop spark-jupyter marimo # stop them again
```

Open http://localhost:8888?token=spark123 — PySpark connected to the same Polaris catalog.

- Pre-configured catalog named `polaris` (same Iceberg tables as Trino)
- Sample notebook in `work/polaris-iceberg-demo.ipynb`
- Write data from Spark, query it from Trino (and vice versa)

```python
# In a notebook cell:
spark.sql("SELECT * FROM polaris.shop.orders").show()
```

### dlt Earthquake Ingestion
The `dlt-earthquakes` service fetches real-time earthquake data from the USGS API and loads it into an Iceberg table via Polaris.

- **Source:** [USGS Earthquake API](https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson) (last 24 hours)
- **Target:** `iceberg.earthquakes.events`
- **Mode:** Append — each run adds the latest batch
- **Runs once** on `podman compose up`, re-run with `podman restart dlt-earthquakes`

```sql
-- Query earthquake data from Trino
SELECT magnitude, place, event_time, depth_km
FROM iceberg.earthquakes.events
ORDER BY magnitude DESC LIMIT 10;

-- Earthquakes by region
SELECT 
  CASE WHEN longitude < -30 THEN 'Americas' WHEN longitude < 60 THEN 'Europe/Africa' ELSE 'Asia/Pacific' END AS region,
  count(*) AS quakes, round(avg(magnitude), 2) AS avg_mag
FROM iceberg.earthquakes.events
GROUP BY 1 ORDER BY 2 DESC;
```

## Federation Examples

```sql
-- Cross-source JOIN: customers (Postgres) + orders (Iceberg/S3)
SELECT c.name, c.country, o.order_id, o.total_amount
FROM iceberg.shop.orders o
JOIN postgres.public.customers c ON o.customer_id = c.customer_id
ORDER BY o.order_date;

-- Full detail across all sources
SELECT c.name, p.name AS product, oi.quantity, oi.unit_price
FROM iceberg.shop.order_items oi
JOIN iceberg.shop.orders o ON oi.order_id = o.order_id
JOIN postgres.public.customers c ON o.customer_id = c.customer_id
JOIN postgres.public.products p ON oi.product_id = p.product_id;

-- Top customers by spend
SELECT c.name, c.country, COUNT(DISTINCT o.order_id) AS orders, SUM(o.total_amount) AS total
FROM iceberg.shop.orders o
JOIN postgres.public.customers c ON o.customer_id = c.customer_id
GROUP BY c.name, c.country
ORDER BY total DESC;
```

## Lifecycle Commands

```bash
# Start everything
podman compose up -d

# Stop (keeps data volumes)
podman compose down

# Stop and wipe all data (fresh start)
podman compose down -v

# View Trino logs
podman logs trino

# View S3 contents
podman exec localstack awslocal s3 ls s3://warehouse/ --recursive --human-readable
```

## Config Files

| File                                  | Purpose                           |
|---------------------------------------|-----------------------------------|
| `docker-compose.yml`                  | Service definitions               |
| `etc/config.properties`               | Trino server config (TLS, auth)   |
| `etc/password-authenticator.properties` | Password auth config            |
| `etc/password.db`                     | User credentials (bcrypt)         |
| `etc/access-control.properties`       | Points to rules.json              |
| `etc/rules.json`                      | Authorization rules (hot-reload)  |
| `etc/catalog/*.properties`            | Catalog connector configs         |
| `init/postgres/init.sql`              | PostgreSQL sample data            |
| `init/polaris/setup.sh`              | Polaris catalog + roles setup     |
| `admin/index.html`                   | Polaris Admin UI (single-page)    |
| `admin/nginx.conf`                   | Nginx config for admin + API proxy|
| `spark/Dockerfile`                   | PySpark+Jupyter image with Iceberg JARs |
| `spark/spark-defaults.conf`          | Spark config (Polaris + S3)       |
| `spark/notebooks/*.ipynb`            | Sample PySpark notebooks          |
| `dlt/Dockerfile`                     | dlt pipeline image                |
| `dlt/pipeline.py`                    | Earthquake ingestion pipeline     |
| `dlt/.dlt/secrets.toml`             | dlt + Polaris catalog config      |
| `sample-queries.sql`                  | Federation query examples         |
