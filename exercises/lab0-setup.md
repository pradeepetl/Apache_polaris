# Lab 0 — Environment Setup

**Level:** 0 (Beginner) | **Time:** 10 minutes

**Goal:** Verify all services are running and run your first Trino query.

---

## Step 1: Check Running Services

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

You should see these containers running:

| Container | Expected Status |
|-----------|----------------|
| trino | Up |
| postgres | Up (healthy) |
| polaris | Up (healthy) |
| localstack | Up (healthy) |
| polaris-admin | Up |

`spark-jupyter` and `marimo` are on-demand and not started by default. Start them when a lab needs them:
```bash
docker compose --profile spark up -d     # Spark Jupyter (:8888)
docker compose --profile marimo up -d    # Marimo (:2718)
docker compose stop spark-jupyter marimo # free the memory again
```

The `polaris-setup`, `localstack-setup`, and `dlt-earthquakes` containers show "Exited (0)" — that's normal, they are one-shot init jobs.

If a service is not running, check logs:
```bash
docker logs <container-name>
```

## Step 2: Open the Web UIs

Open each of these in your browser:

1. **Trino Web UI** — http://localhost:8080
   - Shows running and completed queries
   - No login required (monitoring only)

2. **Polaris Admin** — http://localhost:3000
   - Login: Client ID = `root`, Secret = `s3cr3t`, Realm = `POLARIS`
   - You should see the Dashboard with catalogs and roles

3. **Spark Jupyter** — http://localhost:8888?token=spark123 (after `docker compose --profile spark up -d`)
   - PySpark notebook environment

## Step 3: Your First Trino Query

Connect as admin:

```bash
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure
```

Run:

```sql
SHOW CATALOGS;
```

Expected:
```
  Catalog
-----------
 iceberg
 memory
 postgres
 system
 tpcds
 tpch
```

```sql
SELECT * FROM postgres.public.customers LIMIT 5;
```

You should see customer records with `customer_id`, `name`, `email`, `country`.

```sql
SELECT count(*) AS total_products FROM postgres.public.products;
```

Expected: `20`

Type `quit` to exit the CLI.

## Step 4: One-Off Query (No Interactive CLI)

```bash
docker exec -e TRINO_PASSWORD=admin123 trino \
  trino --server https://localhost:8443 --user admin --password --insecure \
  --execute "SELECT name, country FROM postgres.public.customers ORDER BY country LIMIT 5"
```

## Step 5: Polaris Health Check

```bash
curl -s http://localhost:8182/q/health | python3 -m json.tool
```

Expected: `"status": "UP"`

---

## Checkpoint

- [ ] All services running (`docker ps`)
- [ ] Trino Web UI loads at :8080
- [ ] Polaris Admin loads at :3000 with Dashboard
- [ ] Jupyter loads at :8888
- [ ] `SHOW CATALOGS` returns 6 catalogs
- [ ] `SELECT` from customers returns data

**Next:** [Lab 1 — Exploring Catalogs](lab1-exploring-catalogs.md)
