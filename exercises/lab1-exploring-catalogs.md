# Lab 1 — Exploring Catalogs

**Level:** 1 (Beginner) | **Time:** 15 minutes

**Goal:** Understand how Trino organizes data across catalogs, schemas, and tables.

---

## Concepts

Trino uses a three-level naming hierarchy:

```
catalog.schema.table
```

- **Catalog** — a data source connector (e.g., `postgres`, `iceberg`, `tpch`)
- **Schema** — a namespace within a catalog (e.g., `public`, `shop`, `tiny`)
- **Table** — the actual data

## Step 1: List All Catalogs

Connect as admin:
```bash
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure
```

```sql
SHOW CATALOGS;
```

| Catalog | Backend |
|---------|---------|
| `postgres` | PostgreSQL database |
| `iceberg` | Iceberg tables via Polaris REST Catalog |
| `tpch` | In-memory TPC-H benchmark data |
| `tpcds` | In-memory TPC-DS benchmark data |
| `memory` | JVM heap (empty, create your own) |
| `system` | Trino internal metadata |

## Step 2: Explore Schemas

```sql
SHOW SCHEMAS IN postgres;
SHOW SCHEMAS IN iceberg;
SHOW SCHEMAS IN tpch;
```

**Question:** What schemas exist in `tpch`? What do `tiny`, `sf1`, `sf100` mean?

> They are scale factors. `tiny` has a few hundred rows, `sf1` has ~6M rows in `lineitem`, `sf100` has 600M.

## Step 3: Explore Tables

```sql
SHOW TABLES IN postgres.public;
SHOW TABLES IN iceberg.shop;
SHOW TABLES IN tpch.tiny;
```

## Step 4: Inspect Table Structure

```sql
DESCRIBE postgres.public.customers;
SHOW COLUMNS FROM iceberg.shop.orders;
```

**Question:** What data type is `total_amount` in `iceberg.shop.orders`?

## Step 5: Preview Data

```sql
SELECT * FROM postgres.public.customers LIMIT 5;
SELECT * FROM postgres.public.products LIMIT 5;
SELECT * FROM iceberg.shop.orders LIMIT 5;
SELECT * FROM iceberg.shop.order_items LIMIT 5;
```

**Question:** How are `orders` and `order_items` related? Which column links them?

## Step 6: Basic Aggregations

```sql
-- Customers per country
SELECT country, count(*) AS num_customers
FROM postgres.public.customers
GROUP BY country ORDER BY num_customers DESC;

-- Items per order
SELECT order_id, count(*) AS items, sum(quantity) AS total_qty
FROM iceberg.shop.order_items
GROUP BY order_id ORDER BY total_qty DESC;
```

## Step 7: TPC-H Benchmark Query

```sql
SELECT n.name AS nation, count(*) AS customers
FROM tpch.tiny.customer c
JOIN tpch.tiny.nation n ON c.nationkey = n.nationkey
GROUP BY n.name
ORDER BY customers DESC LIMIT 5;
```

## Step 8: Use the Polaris Admin Data Browser

1. Open http://localhost:3000
2. Click **Data Browser** in the sidebar
3. Expand a catalog > namespace > click a table
4. Observe the schema (columns, types, Iceberg format version, snapshot count)

---

## Exercises

1. Find the most expensive product in `postgres.public.products`.
2. List all distinct `status` values in `iceberg.shop.orders`.
3. How many tables exist in `tpch.sf1`? Same count as `tpch.tiny`?
4. What is the total number of order items in `iceberg.shop.order_items`?
5. In Polaris Admin Data Browser, find the Iceberg format version of `shop.orders`.

**Next:** [Lab 2 — Query Federation](lab2-query-federation.md)
