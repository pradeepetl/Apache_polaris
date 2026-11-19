# Lab 2 — Query Federation

**Level:** 2 (Intermediate) | **Time:** 20 minutes

**Goal:** Join data across Postgres and Iceberg in a single SQL query — Trino's core superpower.

---

## Concepts

**Query federation** = querying multiple data sources in one SQL statement. Without Trino, you'd need ETL to move everything into one system first. With Trino, just use fully-qualified names: `catalog.schema.table`.

## Data Model

```
postgres.public.customers     iceberg.shop.orders       iceberg.shop.order_items
┌──────────────┐             ┌──────────────┐           ┌──────────────┐
│ customer_id  │◄────────────│ customer_id  │           │ order_id     │
│ name         │             │ order_id     │◄──────────│ product_id   │
│ email        │             │ order_date   │           │ quantity     │
│ country      │             │ total_amount │           │ unit_price   │
│ segment      │             │ status       │           │ line_total   │
└──────────────┘             └──────────────┘           └──────────────┘

postgres.public.products
┌──────────────┐
│ product_id   │◄──────── order_items.product_id
│ name         │
│ category     │
│ price        │
└──────────────┘
```

- Customers and Products live in **PostgreSQL**
- Orders and Order Items live in **Iceberg** (on S3 via Polaris)

## Step 1: Simple Cross-Source JOIN

Customers (Postgres) + Orders (Iceberg):

```sql
SELECT
  c.name AS customer,
  c.country,
  o.order_id,
  o.order_date,
  o.total_amount
FROM iceberg.shop.orders o
JOIN postgres.public.customers c
  ON o.customer_id = c.customer_id
ORDER BY o.order_date;
```

**Question:** How many rows? Where does each column come from?

## Step 2: Four-Table Cross-Source JOIN

```sql
SELECT
  c.name AS customer,
  p.name AS product,
  p.category,
  oi.quantity,
  oi.unit_price,
  oi.line_total
FROM iceberg.shop.order_items oi
JOIN iceberg.shop.orders o ON oi.order_id = o.order_id
JOIN postgres.public.customers c ON o.customer_id = c.customer_id
JOIN postgres.public.products p ON oi.product_id = p.product_id
ORDER BY c.name, o.order_id;
```

This single query hits **2 catalogs, 4 tables, 2 different storage backends**.

## Step 3: Aggregations Across Sources

**Top customers by spend:**

```sql
SELECT
  c.name, c.country, c.segment,
  count(DISTINCT o.order_id) AS num_orders,
  round(sum(o.total_amount), 2) AS total_spent
FROM iceberg.shop.orders o
JOIN postgres.public.customers c ON o.customer_id = c.customer_id
GROUP BY c.name, c.country, c.segment
ORDER BY total_spent DESC;
```

**Revenue by product category:**

```sql
SELECT
  p.category,
  count(*) AS items_sold,
  sum(oi.quantity) AS total_qty,
  round(sum(oi.line_total), 2) AS revenue
FROM iceberg.shop.order_items oi
JOIN postgres.public.products p ON oi.product_id = p.product_id
GROUP BY p.category
ORDER BY revenue DESC;
```

## Step 4: Revenue by Country

```sql
SELECT
  c.country,
  count(DISTINCT c.customer_id) AS customers,
  count(DISTINCT o.order_id) AS orders,
  round(sum(o.total_amount), 2) AS total_revenue,
  round(avg(o.total_amount), 2) AS avg_order_value
FROM iceberg.shop.orders o
JOIN postgres.public.customers c ON o.customer_id = c.customer_id
GROUP BY c.country
ORDER BY total_revenue DESC;
```

## Step 5: Using Memory Catalog for Intermediate Results

```sql
CREATE SCHEMA IF NOT EXISTS memory.analytics;

CREATE TABLE memory.analytics.customer_summary AS
SELECT
  c.customer_id, c.name, c.country, c.segment,
  count(DISTINCT o.order_id) AS total_orders,
  round(sum(o.total_amount), 2) AS lifetime_value
FROM iceberg.shop.orders o
JOIN postgres.public.customers c ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.name, c.country, c.segment;

SELECT * FROM memory.analytics.customer_summary
ORDER BY lifetime_value DESC;
```

> Memory catalog data is lost on Trino restart — useful for ad-hoc analysis, not persistence.

## Step 6: Check the Query Plan

1. Open http://localhost:8080
2. Click a completed federation query
3. Look at the **Query Plan** — notice separate `ScanFilterProject` nodes for each catalog

**Question:** Can you identify which parts read from Postgres vs Iceberg?

---

## Exercises

1. **Find customers who have NOT placed any orders.** (Hint: `LEFT JOIN` + check for `NULL`)
2. **What is the most popular product** by quantity sold?
3. **Which country has the highest average order value?**
4. **Create a memory table** with monthly revenue (hint: `date_trunc('month', o.order_date)`)
5. **Bonus:** Join `tpch.tiny.nation` with Postgres customers on `country` — which TPC-H nations match?

**Next:** [Lab 3 — Access Control](lab3-access-control.md)
