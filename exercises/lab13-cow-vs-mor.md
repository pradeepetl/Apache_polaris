# Lab 13 — Copy-on-Write vs Merge-on-Read

**Level:** 5 (Advanced) | **Time:** 30 minutes

**Goal:** Understand the two row-level operation modes in Iceberg — COW rewrites entire files on mutation while MOR writes delta files merged at read time. Compare their performance trade-offs.

---

## Concepts

When you run an UPDATE or DELETE on an Iceberg table, the engine must reconcile the change with immutable Parquet data files. Iceberg supports two strategies:

| Mode | What Happens on Write | What Happens on Read | Best For |
|------|----------------------|---------------------|----------|
| **Copy-on-Write (COW)** | Rewrites the entire affected data file with changes applied | Reads clean, compacted files directly | Read-heavy workloads |
| **Merge-on-Read (MOR)** | Writes a small "delete file" (position or equality deletes) alongside the original data | Merges original data with delete files at query time | Write-heavy workloads |

```
Copy-on-Write (COW)
────────────────────────────────────────────────────────────────────────

  BEFORE UPDATE                        AFTER UPDATE
  ┌────────────────────┐               ┌────────────────────┐
  │   data-001.parquet │               │   data-002.parquet │  (new file)
  │                    │               │                    │
  │  row 1: Alice  10  │  ── UPDATE ─> │  row 1: Alice  99  │  <- changed
  │  row 2: Bob    20  │    row 1      │  row 2: Bob    20  │
  │  row 3: Carol  30  │               │  row 3: Carol  30  │
  └────────────────────┘               └────────────────────┘
         (deleted)                       entire file rewritten


Merge-on-Read (MOR)
────────────────────────────────────────────────────────────────────────

  BEFORE UPDATE                        AFTER UPDATE
  ┌────────────────────┐               ┌────────────────────┐
  │   data-001.parquet │               │   data-001.parquet │  (unchanged)
  │                    │               │                    │
  │  row 1: Alice  10  │  ── UPDATE ─> │  row 1: Alice  10  │
  │  row 2: Bob    20  │    row 1      │  row 2: Bob    20  │
  │  row 3: Carol  30  │               │  row 3: Carol  30  │
  └────────────────────┘               └────────────────────┘
                                        +
                                       ┌────────────────────┐
                                       │  delete-001.parquet │  (tiny file)
                                       │  position delete:   │
                                       │    row 1 deleted    │
                                       └────────────────────┘
                                        +
                                       ┌────────────────────┐
                                       │  data-003.parquet   │  (new value)
                                       │  row 1: Alice  99   │
                                       └────────────────────┘
                                        reads must merge all 3
```

In Trino, the write mode is set via table properties:

```sql
-- For deletes
'write.delete.mode' = 'copy-on-write'   -- or 'merge-on-read'

-- For updates
'write.update.mode' = 'copy-on-write'   -- or 'merge-on-read'

-- For merge operations
'write.merge.mode'  = 'copy-on-write'   -- or 'merge-on-read'
```

**Key point:** The choice between COW and MOR is a classic write-amplification vs read-amplification trade-off. Pick the mode that matches your workload pattern.

---

## Part A: Setup — Two Identical Tables

### Step 1: Create the COW Orders Table

Connect as admin:

```bash
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure
```

```sql
CREATE TABLE iceberg.shop.orders_cow (
  order_id VARCHAR,
  customer_id VARCHAR,
  product VARCHAR,
  quantity INT,
  price DECIMAL(10,2),
  order_date TIMESTAMP(6) WITH TIME ZONE
)
WITH (
  write_delete_mode = 'copy-on-write',
  write_update_mode = 'copy-on-write'
);
```

### Step 2: Create the MOR Orders Table

```sql
CREATE TABLE iceberg.shop.orders_mor (
  order_id VARCHAR,
  customer_id VARCHAR,
  product VARCHAR,
  quantity INT,
  price DECIMAL(10,2),
  order_date TIMESTAMP(6) WITH TIME ZONE
)
WITH (
  write_delete_mode = 'merge-on-read',
  write_update_mode = 'merge-on-read'
);
```

### Step 3: Insert Identical Data into Both Tables

```sql
INSERT INTO iceberg.shop.orders_cow VALUES
  ('ORD001', 'C001', 'Wireless Mouse',      2,  29.99, CURRENT_TIMESTAMP),
  ('ORD002', 'C002', 'Mechanical Keyboard',  1,  89.99, CURRENT_TIMESTAMP),
  ('ORD003', 'C001', 'USB-C Hub',            3,  45.00, CURRENT_TIMESTAMP),
  ('ORD004', 'C003', 'Monitor Stand',         1,  79.50, CURRENT_TIMESTAMP),
  ('ORD005', 'C002', 'Webcam HD',            1,  64.99, CURRENT_TIMESTAMP),
  ('ORD006', 'C004', 'Desk Lamp',            2,  34.99, CURRENT_TIMESTAMP),
  ('ORD007', 'C001', 'Mouse Pad XL',         1,  19.99, CURRENT_TIMESTAMP),
  ('ORD008', 'C005', 'USB Microphone',       1, 129.00, CURRENT_TIMESTAMP),
  ('ORD009', 'C003', 'HDMI Cable',           4,  12.99, CURRENT_TIMESTAMP),
  ('ORD010', 'C002', 'Laptop Stand',         1,  54.99, CURRENT_TIMESTAMP),
  ('ORD011', 'C004', 'Wireless Charger',     2,  24.99, CURRENT_TIMESTAMP),
  ('ORD012', 'C005', 'Screen Protector',     3,   9.99, CURRENT_TIMESTAMP),
  ('ORD013', 'C001', 'Bluetooth Speaker',    1,  39.99, CURRENT_TIMESTAMP),
  ('ORD014', 'C003', 'Power Strip',          1,  22.50, CURRENT_TIMESTAMP),
  ('ORD015', 'C004', 'Cable Organizer',      2,  14.99, CURRENT_TIMESTAMP);

INSERT INTO iceberg.shop.orders_mor VALUES
  ('ORD001', 'C001', 'Wireless Mouse',      2,  29.99, CURRENT_TIMESTAMP),
  ('ORD002', 'C002', 'Mechanical Keyboard',  1,  89.99, CURRENT_TIMESTAMP),
  ('ORD003', 'C001', 'USB-C Hub',            3,  45.00, CURRENT_TIMESTAMP),
  ('ORD004', 'C003', 'Monitor Stand',         1,  79.50, CURRENT_TIMESTAMP),
  ('ORD005', 'C002', 'Webcam HD',            1,  64.99, CURRENT_TIMESTAMP),
  ('ORD006', 'C004', 'Desk Lamp',            2,  34.99, CURRENT_TIMESTAMP),
  ('ORD007', 'C001', 'Mouse Pad XL',         1,  19.99, CURRENT_TIMESTAMP),
  ('ORD008', 'C005', 'USB Microphone',       1, 129.00, CURRENT_TIMESTAMP),
  ('ORD009', 'C003', 'HDMI Cable',           4,  12.99, CURRENT_TIMESTAMP),
  ('ORD010', 'C002', 'Laptop Stand',         1,  54.99, CURRENT_TIMESTAMP),
  ('ORD011', 'C004', 'Wireless Charger',     2,  24.99, CURRENT_TIMESTAMP),
  ('ORD012', 'C005', 'Screen Protector',     3,   9.99, CURRENT_TIMESTAMP),
  ('ORD013', 'C001', 'Bluetooth Speaker',    1,  39.99, CURRENT_TIMESTAMP),
  ('ORD014', 'C003', 'Power Strip',          1,  22.50, CURRENT_TIMESTAMP),
  ('ORD015', 'C004', 'Cable Organizer',      2,  14.99, CURRENT_TIMESTAMP);
```

Verify both tables have the same row count:

```sql
SELECT 'COW' AS mode, COUNT(*) AS rows FROM iceberg.shop.orders_cow
UNION ALL
SELECT 'MOR' AS mode, COUNT(*) AS rows FROM iceberg.shop.orders_mor;
```

---

## Part B: Compare Write Performance

### Step 4: Check File Counts Before Mutations

```sql
SELECT 'COW' AS mode, COUNT(*) AS file_count, SUM(file_size_in_bytes) AS total_bytes
FROM iceberg.shop."orders_cow$files";

SELECT 'MOR' AS mode, COUNT(*) AS file_count, SUM(file_size_in_bytes) AS total_bytes
FROM iceberg.shop."orders_mor$files";
```

Both tables should have the same number of data files at this point — no mutations have happened yet.

### Step 5: Update the COW Table (Timed)

Update the quantity for 5 orders. Note the execution time reported by Trino:

```sql
UPDATE iceberg.shop.orders_cow
SET quantity = quantity + 10
WHERE order_id IN ('ORD001', 'ORD003', 'ORD005', 'ORD007', 'ORD009');
```

COW must rewrite every data file that contains an affected row. Watch the time reported in the Trino output.

### Step 6: Run the Same Update on the MOR Table (Timed)

```sql
UPDATE iceberg.shop.orders_mor
SET quantity = quantity + 10
WHERE order_id IN ('ORD001', 'ORD003', 'ORD005', 'ORD007', 'ORD009');
```

MOR only writes small delete files plus the new values. This should be faster (or at least produce fewer file rewrites).

### Step 7: Compare File States After Mutation

Check the COW table files:

```sql
SELECT file_path, content, record_count, file_size_in_bytes
FROM iceberg.shop."orders_cow$files";
```

Check the MOR table files:

```sql
SELECT file_path, content, record_count, file_size_in_bytes
FROM iceberg.shop."orders_mor$files";
```

**What to look for:**
- COW: The original data files are gone, replaced by newly written files containing the updated data.
- MOR: The original data files remain, with additional delete files (content = `POSITION_DELETES` or `EQUALITY_DELETES`) alongside them.

---

## Part C: Compare Read Performance

### Step 8: Aggregation Query on COW Table (Timed)

```sql
SELECT
  customer_id,
  COUNT(*) AS order_count,
  SUM(quantity * price) AS total_value
FROM iceberg.shop.orders_cow
GROUP BY customer_id
ORDER BY total_value DESC;
```

Note the query time. COW reads clean, compacted files — no merge overhead.

### Step 9: Same Aggregation on MOR Table (Timed)

```sql
SELECT
  customer_id,
  COUNT(*) AS order_count,
  SUM(quantity * price) AS total_value
FROM iceberg.shop.orders_mor
GROUP BY customer_id
ORDER BY total_value DESC;
```

MOR must merge the original data with the delete files at read time. At this small scale the difference is tiny, but at production scale (millions of rows, hundreds of delete files) the overhead becomes significant.

### Step 10: Delete on Both Tables and Compare

Delete 3 orders from both tables:

```sql
DELETE FROM iceberg.shop.orders_cow
WHERE order_id IN ('ORD012', 'ORD014', 'ORD015');

DELETE FROM iceberg.shop.orders_mor
WHERE order_id IN ('ORD012', 'ORD014', 'ORD015');
```

Check file state again:

```sql
-- COW: files are rewritten without the deleted rows
SELECT content, COUNT(*) AS cnt, SUM(record_count) AS total_records
FROM iceberg.shop."orders_cow$files"
GROUP BY content;

-- MOR: new delete files appear
SELECT content, COUNT(*) AS cnt, SUM(record_count) AS total_records
FROM iceberg.shop."orders_mor$files"
GROUP BY content;
```

---

## Part D: When to Use Each

```
Aspect           COW                          MOR
──────────────── ──────────────────────────── ────────────────────────────
Write speed      Slower (rewrites files)      Faster (small delta files)
Read speed       Faster (clean files)         Slower (must merge at read)
Storage          Less (compacted after write)  More (data + delete files)
File count       Fewer (rewritten in place)    More (accumulates deletes)
Best for         Read-heavy workloads         Write-heavy workloads
Compaction need  Low                          High (merge deletes back)
Examples         BI dashboards, reporting     IoT ingestion, CDC streams
```

**Rule of thumb:** If your table is read 100x more than it is written, use COW. If you have frequent small updates/deletes and can tolerate slightly slower reads (or run periodic compaction), use MOR.

---

## Exercises

1. **Bulk write benchmark** — Insert 50 more rows into both tables, then run 10 separate UPDATE statements on each (updating different rows each time). Compare the total wall-clock time for all writes on COW vs MOR.

2. **Query plan analysis** — Run `EXPLAIN ANALYZE` on the aggregation query (Step 8/9) on both tables after all mutations. Look for differences in the plan — MOR may show additional merge or filter stages.

3. **Compaction restores read performance** — Run `ALTER TABLE iceberg.shop.orders_mor EXECUTE optimize` to compact the MOR table. Then re-run the aggregation query. How does the read performance and file layout change compared to before compaction?

4. **Mixed mode table** — Create a table with `write.delete.mode = 'copy-on-write'` and `write.update.mode = 'merge-on-read'`. When would this combination make sense? Test it by running both DELETEs and UPDATEs and inspecting the file metadata.

5. **Challenge: Automated benchmark** — Write a SQL script (or series of queries) that runs N updates on both tables, captures the Trino-reported wall time for each, and produces a summary. Include a final read query on each table so you can compare total write-time + read-time for both modes.

**Congratulations!** You now understand the fundamental write-path trade-off in Iceberg. Choosing between COW and MOR is one of the most impactful performance decisions when designing Iceberg tables — and Polaris lets you manage these table properties centrally across all engines.
