# Lab 10 — Time Travel

**Level:** 5 (Advanced) | **Time:** 25 minutes

**Goal:** Query historical table states, compare versions, and rollback to previous snapshots using Iceberg's time travel capabilities.

---

## Concepts

Every write operation in Iceberg creates an **immutable snapshot** — a complete picture of the table at that moment. This gives you three powerful capabilities:

| Capability | Description | Use Case |
|------------|-------------|----------|
| **Snapshots** | Every INSERT, UPDATE, or DELETE creates a new snapshot | Full audit trail of every change |
| **Time Travel** | Query any past state by timestamp or snapshot ID | Reproduce past results, debug issues |
| **Rollback** | Revert the table to a previous snapshot | Recover from bad writes or accidental deletes |

```
Snapshot Chain
──────────────────────────────────────────────────────────────────────────

  [Snap 1]          [Snap 2]          [Snap 3]          [Current]
  ┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐
  │ CREATE + │─────>│ UPDATE   │─────>│ DELETE   │─────>│ ROLLBACK │
  │ INSERT   │      │ quantity │      │ product  │      │ to Snap 2│
  │          │      │          │      │          │      │          │
  │ 5 rows   │      │ 5 rows   │      │ 4 rows   │      │ 5 rows   │
  └──────────┘      └──────────┘      └──────────┘      └──────────┘
       ^                 ^                                    │
       │                 │                                    │
       │                 └────────────────────────────────────┘
       │                        rollback restores this state
       │
  FOR TIMESTAMP AS OF '...'
  FOR VERSION AS OF <id>
       query any past state
```

**Key point:** Polaris stores the metadata for every snapshot. You can time-travel from any engine (Trino, Spark, PyIceberg) and always see a consistent history.

---

## Part A: Build a Snapshot History

### Step 1: Create the Inventory Table

Connect as admin:

```bash
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure
```

```sql
CREATE TABLE iceberg.shop.inventory (
  product_id VARCHAR,
  product_name VARCHAR,
  quantity INT,
  last_updated TIMESTAMP(6) WITH TIME ZONE
);
```

### Step 2: Insert Initial Inventory (Snapshot 1)

```sql
INSERT INTO iceberg.shop.inventory VALUES
  ('P001', 'Wireless Mouse',     150, CURRENT_TIMESTAMP),
  ('P002', 'Mechanical Keyboard', 75, CURRENT_TIMESTAMP),
  ('P003', 'USB-C Hub',          200, CURRENT_TIMESTAMP),
  ('P004', 'Monitor Stand',       50, CURRENT_TIMESTAMP),
  ('P005', 'Webcam HD',          120, CURRENT_TIMESTAMP);
```

### Step 3: View Snapshot History

```sql
SELECT
  snapshot_id,
  parent_id,
  operation,
  committed_at
FROM iceberg.shop."inventory$snapshots"
ORDER BY committed_at;
```

You should see **1 snapshot** from the INSERT. Note the `committed_at` timestamp and `snapshot_id` — you will need them for time travel.

### Step 4: Update Quantities — Simulate a Restock (Snapshot 2)

```sql
UPDATE iceberg.shop.inventory
SET quantity = quantity + 100,
    last_updated = CURRENT_TIMESTAMP
WHERE product_id = 'P001';
```

### Step 5: Delete a Product — Discontinue an Item (Snapshot 3)

```sql
DELETE FROM iceberg.shop.inventory
WHERE product_id = 'P005';
```

### Step 6: View All 3 Snapshots

```sql
SELECT
  snapshot_id,
  parent_id,
  operation,
  committed_at,
  summary
FROM iceberg.shop."inventory$snapshots"
ORDER BY committed_at;
```

You should now see 3 snapshots:

| # | Operation | What happened |
|---|-----------|---------------|
| 1 | `append`  | Initial 5-row insert |
| 2 | `overwrite` | Updated P001 quantity |
| 3 | `delete`  | Removed P005 |

---

## Part B: Time Travel Queries

### Step 7: Query the Original State (Timestamp-Based)

Use the `committed_at` value from Snapshot 1 (the INSERT). Copy the timestamp from your Step 6 output:

```sql
-- Replace the timestamp with the committed_at from your first snapshot
SELECT *
FROM iceberg.shop.inventory
FOR TIMESTAMP AS OF TIMESTAMP '2025-01-15 10:30:00.000 UTC';
```

You should see all 5 products with the **original** quantities (P001 has 150, P005 exists).

**How it works:** Iceberg finds the latest snapshot whose `committed_at` is at or before the given timestamp, then reads data files from that snapshot.

### Step 8: Query by Snapshot ID (Version-Based)

Use the `snapshot_id` from your first snapshot:

```sql
-- Replace with the actual snapshot_id from your Step 6 output
SELECT *
FROM iceberg.shop.inventory
FOR VERSION AS OF 1234567890123456789;
```

This returns the exact same result — but uses the snapshot ID instead of a timestamp. Version-based travel is precise: it always returns the exact snapshot you requested.

### Step 9: Compare Current vs Historical State

This is where time travel becomes truly useful. Join the current table against a past version to see exactly what changed:

```sql
-- Replace <first_snapshot_id> with your actual Snapshot 1 ID
SELECT
  COALESCE(c.product_id, h.product_id) AS product_id,
  h.product_name AS original_name,
  h.quantity AS original_qty,
  c.quantity AS current_qty,
  c.quantity - h.quantity AS qty_change,
  CASE
    WHEN c.product_id IS NULL THEN 'DELETED'
    WHEN h.product_id IS NULL THEN 'ADDED'
    WHEN c.quantity <> h.quantity THEN 'MODIFIED'
    ELSE 'UNCHANGED'
  END AS status
FROM iceberg.shop.inventory c
FULL OUTER JOIN iceberg.shop.inventory FOR VERSION AS OF <first_snapshot_id> h
  ON c.product_id = h.product_id
ORDER BY COALESCE(c.product_id, h.product_id);
```

Expected output:

| product_id | original_qty | current_qty | qty_change | status |
|------------|-------------|-------------|------------|--------|
| P001       | 150         | 250         | 100        | MODIFIED |
| P002       | 75          | 75          | 0          | UNCHANGED |
| P003       | 200         | 200         | 0          | UNCHANGED |
| P004       | 50          | 50          | 0          | UNCHANGED |
| P005       | 120         | NULL        | NULL       | DELETED |

---

## Part C: Rollback

### Step 10: Rollback to Before the Delete

Find the snapshot ID for Snapshot 2 (after the UPDATE but before the DELETE):

```sql
-- Get the snapshot_id for the second snapshot
SELECT snapshot_id, operation, committed_at
FROM iceberg.shop."inventory$snapshots"
ORDER BY committed_at;
```

Now rollback:

```sql
-- Replace <snapshot_2_id> with the actual snapshot ID
CALL iceberg.system.rollback_to_snapshot('shop', 'inventory', <snapshot_2_id>);
```

### Step 11: Verify the Rollback

```sql
SELECT * FROM iceberg.shop.inventory ORDER BY product_id;
```

**P005 (Webcam HD) is back!** The table now shows the state as it was after the restock update but before the delete.

Check the snapshot history:

```sql
SELECT
  snapshot_id,
  parent_id,
  operation,
  committed_at
FROM iceberg.shop."inventory$snapshots"
ORDER BY committed_at;
```

The rollback does not erase history. All original snapshots remain. The current table pointer simply moves back to Snapshot 2.

### Step 12: Use Cases

Time travel and rollback are essential for:

```
Use Case                     How Time Travel Helps
─────────────────────────── ──────────────────────────────────────────────────
Auditing & compliance        Query the exact table state at any point in time
Recovering from bad writes   Rollback to the last known good snapshot
Debugging data pipelines     Compare before/after to find what changed
Reproducible analytics       Re-run a report as of a specific date
Regulatory reporting         Prove what data looked like on a given date
A/B testing data changes     Compare two versions side by side
```

---

## Exercises

1. **Add more mutations** — Insert 3 new products, update 2 existing ones, then delete 1. Use `"inventory$snapshots"` to verify 3 new snapshots were created.

2. **Time travel to every snapshot** — Write a query for each snapshot in the history. Confirm the row count matches expectations at each point.

3. **Compare any two snapshots** — Adapt the Step 9 comparison query to compare Snapshot 1 vs Snapshot 3 (skipping Snapshot 2). What does the diff look like?

4. **Rollback chain** — Rollback to the original Snapshot 1 (before any updates). Verify all 5 products have their original quantities. Then think about: can you "undo" a rollback?

5. **Challenge: Build a changelog query** — Write a single SQL query that shows what changed between two specific snapshots. For each row, show the `product_id`, the old values, the new values, and a status column (`ADDED`, `DELETED`, `MODIFIED`, `UNCHANGED`). Test it across multiple snapshot pairs.

   *Hint:* Use `FULL OUTER JOIN` between `FOR VERSION AS OF <old_id>` and `FOR VERSION AS OF <new_id>`, similar to Step 9 but with two versioned references instead of one.

**Congratulations!** You can now query any historical state, compare versions, and recover from mistakes — all powered by Iceberg's immutable snapshot architecture and Polaris as the central catalog.
