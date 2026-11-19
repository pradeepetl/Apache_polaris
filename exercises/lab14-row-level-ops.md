# Lab 14 — Row-Level Operations (UPDATE, DELETE, MERGE)

**Level:** 4 (Intermediate) | **Time:** 30 minutes

**Goal:** Master Iceberg's row-level mutation operations — UPDATE, DELETE, and MERGE INTO — and understand how each creates snapshots that enable time travel.

---

## Concepts

Unlike traditional Hive tables (which only support INSERT and full-partition overwrite), Iceberg supports **full row-level operations**: UPDATE, DELETE, and MERGE INTO. Each mutation creates a new **immutable snapshot**, giving you a complete audit trail and the ability to time-travel to any prior state.

| Operation | What It Does | Snapshot Type |
|-----------|-------------|---------------|
| **UPDATE** | Modify columns in existing rows that match a condition | `overwrite` |
| **DELETE** | Remove rows that match a condition | `delete` |
| **MERGE INTO** | Upsert: update matched rows, insert unmatched rows | `overwrite` |

```
Row-Level Operations and Snapshots
────────────────────────────────────────────────────────────────────────────

  [Snap 1]            [Snap 2]            [Snap 3]            [Snap 4]
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │ INSERT       │───>│ UPDATE       │───>│ DELETE       │───>│ MERGE INTO   │
  │ 10 customers │    │ tier changes │    │ removed 2    │    │ upserted 5   │
  │              │    │              │    │              │    │              │
  │ 10 rows      │    │ 10 rows      │    │ 8 rows       │    │ 11 rows      │
  └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
                                                                    │
  Every operation is a new snapshot.                                 │
  Time travel lets you see any prior state.                         │
  Rollback lets you revert to any snapshot.  <──────────────────────┘
```

**MERGE INTO** is the most powerful operation — it combines UPDATE and INSERT into a single atomic statement (the "upsert" pattern):

- **WHEN MATCHED** — the row already exists in the target table: update it (or delete it)
- **WHEN NOT MATCHED** — the row is new: insert it

This is the standard pattern for incremental data loads.

---

## Part A: Setup

### Step 1: Create the Customers Table

Connect as admin:

```bash
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure
```

```sql
CREATE SCHEMA IF NOT EXISTS iceberg.shop;

CREATE TABLE iceberg.shop.customers (
  customer_id VARCHAR,
  name VARCHAR,
  email VARCHAR,
  tier VARCHAR,
  total_spent DECIMAL(10,2),
  signup_date DATE
);
```

### Step 2: Insert 10 Customers

```sql
INSERT INTO iceberg.shop.customers VALUES
  ('C001', 'Alice Johnson',   'Alice.Johnson@example.com',   'gold',   750.00, DATE '2024-01-15'),
  ('C002', 'Bob Smith',       'Bob.Smith@example.com',       'silver', 320.50, DATE '2024-02-20'),
  ('C003', 'Carol Davis',     'CAROL.DAVIS@example.com',     'bronze',  45.00, DATE '2024-03-10'),
  ('C004', 'David Wilson',    'David.Wilson@EXAMPLE.COM',    'silver', 510.75, DATE '2024-04-05'),
  ('C005', 'Eve Martinez',    'Eve.Martinez@example.com',    'gold',   920.00, DATE '2024-05-12'),
  ('C006', 'Frank Brown',     'FRANK.BROWN@example.com',     'bronze',  30.00, DATE '2024-06-18'),
  ('C007', 'Grace Lee',       'Grace.Lee@example.com',       'silver', 275.25, DATE '2024-07-22'),
  ('C008', 'Henry Taylor',    'Henry.Taylor@example.com',    'gold',   680.00, DATE '2024-08-30'),
  ('C009', 'Iris Chen',       'Iris.Chen@example.com',       'bronze',  15.50, DATE '2024-09-14'),
  ('C010', 'Jack Anderson',   'Jack.Anderson@example.com',   'silver', 490.00, DATE '2024-10-01');
```

Verify:

```sql
SELECT * FROM iceberg.shop.customers ORDER BY customer_id;
```

You should see 10 rows with a mix of bronze, silver, and gold tiers.

---

## Part B: UPDATE Operations

### Step 3: Simple UPDATE — Promote High Spenders to Gold

Customers who have spent more than $500 deserve the gold tier:

```sql
UPDATE iceberg.shop.customers
SET tier = 'gold'
WHERE total_spent > 500 AND tier <> 'gold';
```

Verify:

```sql
SELECT customer_id, name, tier, total_spent
FROM iceberg.shop.customers
WHERE tier = 'gold'
ORDER BY customer_id;
```

David Wilson (C004, $510.75) should now be gold alongside Alice, Eve, and Henry.

### Step 4: Conditional UPDATE — Loyalty Bonus for Gold Customers

Give all gold-tier customers a 10% spending bonus:

```sql
UPDATE iceberg.shop.customers
SET total_spent = total_spent * 1.10
WHERE tier = 'gold';
```

Verify:

```sql
SELECT customer_id, name, tier, total_spent
FROM iceberg.shop.customers
WHERE tier = 'gold'
ORDER BY customer_id;
```

### Step 5: Check Snapshot Count

Every operation creates a snapshot. You should now have 3 (INSERT + 2 UPDATEs):

```sql
SELECT
  snapshot_id,
  parent_id,
  operation,
  committed_at
FROM iceberg.shop."customers$snapshots"
ORDER BY committed_at;
```

| # | Operation | What happened |
|---|-----------|---------------|
| 1 | `append`  | Initial 10-row insert |
| 2 | `overwrite` | Promoted high spenders to gold |
| 3 | `overwrite` | Applied 10% loyalty bonus |

---

## Part C: DELETE Operations

### Step 6: DELETE Low-Activity Customers

Remove customers who have spent less than $50:

```sql
DELETE FROM iceberg.shop.customers
WHERE total_spent < 50;
```

### Step 7: Verify the Delete

```sql
SELECT COUNT(*) AS remaining_customers FROM iceberg.shop.customers;
```

```sql
SELECT customer_id, name, total_spent
FROM iceberg.shop.customers
ORDER BY customer_id;
```

Carol Davis (C003, $45.00), Frank Brown (C006, $30.00), and Iris Chen (C009, $15.50) should be gone. You should have 7 rows remaining.

### Step 8: Time Travel to See Deleted Rows

The deleted rows still exist in previous snapshots. Find the snapshot before the DELETE:

```sql
SELECT snapshot_id, operation, committed_at
FROM iceberg.shop."customers$snapshots"
ORDER BY committed_at;
```

Use the snapshot ID from snapshot 3 (the last UPDATE, before the DELETE):

```sql
-- Replace <snapshot_3_id> with the actual snapshot ID
SELECT customer_id, name, total_spent
FROM iceberg.shop.customers
FOR VERSION AS OF <snapshot_3_id>
WHERE total_spent < 50
ORDER BY customer_id;
```

You should see Carol, Frank, and Iris — they are gone from the current table but preserved in the snapshot history.

---

## Part D: MERGE INTO (Upsert)

### Step 9: Create a Staging Table

Create a staging table with a mix of existing customers (updated data) and new customers:

```sql
CREATE TABLE iceberg.shop.customers_staging (
  customer_id VARCHAR,
  name VARCHAR,
  email VARCHAR,
  tier VARCHAR,
  total_spent DECIMAL(10,2),
  signup_date DATE
);

INSERT INTO iceberg.shop.customers_staging VALUES
  ('C001', 'Alice Johnson',   'alice.johnson@example.com',   'gold',  1200.00, DATE '2024-01-15'),
  ('C002', 'Bob Smith',       'bob.smith@example.com',       'gold',   600.00, DATE '2024-02-20'),
  ('C010', 'Jack Anderson',   'jack.anderson@example.com',   'gold',   800.00, DATE '2024-10-01'),
  ('C011', 'Karen White',     'karen.white@example.com',     'silver', 350.00, DATE '2025-01-10'),
  ('C012', 'Leo Garcia',      'leo.garcia@example.com',      'bronze', 120.00, DATE '2025-02-15');
```

This staging table contains:
- **C001, C002, C010** — existing customers with higher spend amounts (should be updated)
- **C011, C012** — brand new customers (should be inserted)

### Step 10: MERGE INTO

Match on `customer_id`. When a match exists and the staging data shows higher spending, update. When no match exists, insert:

```sql
MERGE INTO iceberg.shop.customers AS target
USING iceberg.shop.customers_staging AS staging
ON target.customer_id = staging.customer_id
WHEN MATCHED AND staging.total_spent > target.total_spent THEN
  UPDATE SET
    email = staging.email,
    tier = staging.tier,
    total_spent = staging.total_spent
WHEN NOT MATCHED THEN
  INSERT (customer_id, name, email, tier, total_spent, signup_date)
  VALUES (staging.customer_id, staging.name, staging.email, staging.tier, staging.total_spent, staging.signup_date);
```

### Step 11: Verify the MERGE Results

```sql
SELECT customer_id, name, tier, total_spent
FROM iceberg.shop.customers
ORDER BY customer_id;
```

Expected results:
- **C001** (Alice) — total_spent updated to $1200.00
- **C002** (Bob) — total_spent updated to $600.00
- **C010** (Jack) — total_spent updated to $800.00
- **C011** (Karen) — newly inserted
- **C012** (Leo) — newly inserted
- Other existing customers — unchanged

### Step 12: Full Snapshot History

Every operation has been tracked:

```sql
SELECT
  snapshot_id,
  parent_id,
  operation,
  committed_at
FROM iceberg.shop."customers$snapshots"
ORDER BY committed_at;
```

You should see snapshots for every mutation:

| # | Operation | What happened |
|---|-----------|---------------|
| 1 | `append`  | Initial 10-row insert |
| 2 | `overwrite` | Promoted high spenders to gold |
| 3 | `overwrite` | Applied 10% loyalty bonus |
| 4 | `delete`  | Removed low-activity customers |
| 5 | `overwrite` | MERGE — updated 3 + inserted 2 |

---

## Part E: Combining with Time Travel

### Step 13: Compare Current State vs Original State

Use a time-travel JOIN to build a full diff showing which customers were ADDED, MODIFIED, or DELETED since the beginning:

```sql
-- Replace <first_snapshot_id> with the snapshot ID from snapshot 1
SELECT
  COALESCE(c.customer_id, h.customer_id) AS customer_id,
  h.name AS original_name,
  h.tier AS original_tier,
  h.total_spent AS original_spent,
  c.name AS current_name,
  c.tier AS current_tier,
  c.total_spent AS current_spent,
  CASE
    WHEN c.customer_id IS NULL THEN 'DELETED'
    WHEN h.customer_id IS NULL THEN 'ADDED'
    WHEN c.total_spent <> h.total_spent OR c.tier <> h.tier THEN 'MODIFIED'
    ELSE 'UNCHANGED'
  END AS status
FROM iceberg.shop.customers c
FULL OUTER JOIN iceberg.shop.customers FOR VERSION AS OF <first_snapshot_id> h
  ON c.customer_id = h.customer_id
ORDER BY COALESCE(c.customer_id, h.customer_id);
```

Expected output:

| customer_id | original_tier | original_spent | current_tier | current_spent | status |
|-------------|---------------|----------------|--------------|---------------|--------|
| C001 | gold | 750.00 | gold | 1200.00 | MODIFIED |
| C002 | silver | 320.50 | gold | 600.00 | MODIFIED |
| C003 | bronze | 45.00 | NULL | NULL | DELETED |
| C004 | silver | 510.75 | gold | 561.83 | MODIFIED |
| C005 | gold | 920.00 | gold | 1012.00 | MODIFIED |
| C006 | bronze | 30.00 | NULL | NULL | DELETED |
| C007 | silver | 275.25 | silver | 275.25 | UNCHANGED |
| C008 | gold | 680.00 | gold | 748.00 | MODIFIED |
| C009 | bronze | 15.50 | NULL | NULL | DELETED |
| C010 | silver | 490.00 | gold | 800.00 | MODIFIED |
| C011 | NULL | NULL | silver | 350.00 | ADDED |
| C012 | NULL | NULL | bronze | 120.00 | ADDED |

---

## Exercises

1. **Lowercase all emails** — Run an UPDATE that sets all email addresses to lowercase using `LOWER(email)`. Then use time travel to verify the old mixed-case emails are still accessible in the previous snapshot.

2. **DELETE and rollback** — DELETE all bronze-tier customers. Then use `CALL iceberg.system.rollback_to_snapshot` to undo the delete. Verify the bronze customers are back.

3. **Three-way MERGE** — Create a new staging table and write a MERGE with three conditions:
   - `WHEN MATCHED AND staging.total_spent > target.total_spent THEN UPDATE`
   - `WHEN MATCHED AND staging.total_spent < target.total_spent THEN DELETE`
   - `WHEN NOT MATCHED THEN INSERT`

   Verify that all three actions occurred.

4. **Inspect snapshot metadata** — Query `iceberg.shop."customers$snapshots"` and examine every row. How many snapshots exist? What operation type does each show? Look at the `summary` column — what additional details does Iceberg record for each operation?

5. **Challenge: Incremental load pipeline** — Write a complete incremental load sequence:
   - Create a new staging table with fresh data (some overlapping, some new customer IDs)
   - MERGE it into the customers table
   - Query the snapshot history to determine how many rows were inserted vs updated
   - Compare the before-MERGE and after-MERGE snapshots using a time-travel JOIN to produce a detailed changelog

   *Hint:* Use the `summary` field in `"customers$snapshots"` — it contains keys like `added-records` and `changed-partition-count` that tell you exactly what happened.

**Congratulations!** You can now perform row-level mutations (UPDATE, DELETE, MERGE INTO) on Iceberg tables, with every change tracked as an immutable snapshot — enabling full audit trails, time travel, and rollback through Polaris.
