# Lab 11 — Hidden Partitioning & Partition Evolution

**Level:** 5 (Advanced) | **Time:** 30 minutes

**Goal:** Understand Iceberg's hidden partition transforms, demonstrate partition pruning, and evolve partition specs without rewriting data.

---

## Concepts

### Traditional (Hive) Partitioning vs Iceberg Hidden Partitioning

**Hive-style partitioning** requires the user to manage partition columns explicitly. The partition column appears in every query, the directory layout leaks into SQL, and adding or changing partitions means rewriting the entire table.

**Iceberg hidden partitions** apply transforms automatically at write time. Queries are partition-unaware — users write normal `WHERE` clauses and Iceberg translates them to partition filters behind the scenes.

```
Available Transforms:
─────────────────────────────────────────────────────────
  year(ts)           → partition by year    (2026)
  month(ts)          → partition by month   (2026-09)
  day(ts)            → partition by day     (2026-09-23)
  hour(ts)           → partition by hour    (2026-09-23-14)
  bucket(N, col)     → hash into N buckets  (0, 1, ..., N-1)
  truncate(N, col)   → truncate to width N  ("abc" → "ab" if N=2)
```

### How Hidden Partitioning Works

```
  INSERT INTO web_events (event_time, user_id, ...)
  VALUES ('2026-09-23 10:15:00', 'user-42', ...)

        ┌──────────────────────────────────────────┐
        │  Iceberg applies: day(event_time)        │
        │                   bucket(4, user_id)     │
        └──────────────────┬───────────────────────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
    event_time_day=    event_time_day=   event_time_day=
      2026-09-23         2026-09-24       2026-09-25
      ├── bucket=0       ├── bucket=0     ├── bucket=0
      ├── bucket=1       ├── bucket=1     ├── bucket=1
      ├── bucket=2       ├── bucket=2     ├── bucket=2
      └── bucket=3       └── bucket=3     └── bucket=3

  Query: WHERE event_time > '2026-09-24'
         → Iceberg prunes 2026-09-23 partitions automatically
         → User never mentions a partition column!
```

**Key point:** The partition layout is metadata-only. Users write business queries; Iceberg handles the mapping.

---

## Part A: Hidden Partitioning & Partition Pruning

### Step 1: Create the Web Events Table

Connect as admin:

```bash
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure
```

```sql
CREATE TABLE iceberg.shop.web_events (
  event_id VARCHAR,
  user_id VARCHAR,
  event_type VARCHAR,
  page VARCHAR,
  event_time TIMESTAMP(6) WITH TIME ZONE,
  country VARCHAR
)
WITH (
  partitioning = ARRAY['day(event_time)', 'bucket(4, user_id)']
);
```

This creates a table with two hidden partition transforms:
- `day(event_time)` — organizes data by calendar day
- `bucket(4, user_id)` — distributes users across 4 hash buckets

### Step 2: Insert Sample Data (30 Rows Across 3 Days)

```sql
-- Day 1: 2026-09-23 — 10 events
INSERT INTO iceberg.shop.web_events VALUES ('evt-001', 'user-01', 'page_view', '/home', TIMESTAMP '2026-09-23 08:15:00 UTC', 'US');
INSERT INTO iceberg.shop.web_events VALUES ('evt-002', 'user-02', 'click', '/products', TIMESTAMP '2026-09-23 09:22:00 UTC', 'UK');
INSERT INTO iceberg.shop.web_events VALUES ('evt-003', 'user-03', 'page_view', '/about', TIMESTAMP '2026-09-23 10:05:00 UTC', 'DE');
INSERT INTO iceberg.shop.web_events VALUES ('evt-004', 'user-04', 'purchase', '/checkout', TIMESTAMP '2026-09-23 11:30:00 UTC', 'US');
INSERT INTO iceberg.shop.web_events VALUES ('evt-005', 'user-01', 'click', '/products/42', TIMESTAMP '2026-09-23 12:45:00 UTC', 'US');
INSERT INTO iceberg.shop.web_events VALUES ('evt-006', 'user-05', 'page_view', '/home', TIMESTAMP '2026-09-23 13:10:00 UTC', 'FR');
INSERT INTO iceberg.shop.web_events VALUES ('evt-007', 'user-06', 'click', '/blog', TIMESTAMP '2026-09-23 14:00:00 UTC', 'JP');
INSERT INTO iceberg.shop.web_events VALUES ('evt-008', 'user-02', 'purchase', '/checkout', TIMESTAMP '2026-09-23 15:20:00 UTC', 'UK');
INSERT INTO iceberg.shop.web_events VALUES ('evt-009', 'user-07', 'page_view', '/pricing', TIMESTAMP '2026-09-23 16:35:00 UTC', 'IN');
INSERT INTO iceberg.shop.web_events VALUES ('evt-010', 'user-08', 'click', '/docs', TIMESTAMP '2026-09-23 17:50:00 UTC', 'BR');

-- Day 2: 2026-09-24 — 10 events
INSERT INTO iceberg.shop.web_events VALUES ('evt-011', 'user-01', 'page_view', '/home', TIMESTAMP '2026-09-24 07:10:00 UTC', 'US');
INSERT INTO iceberg.shop.web_events VALUES ('evt-012', 'user-03', 'click', '/products/99', TIMESTAMP '2026-09-24 08:25:00 UTC', 'DE');
INSERT INTO iceberg.shop.web_events VALUES ('evt-013', 'user-09', 'page_view', '/home', TIMESTAMP '2026-09-24 09:40:00 UTC', 'CA');
INSERT INTO iceberg.shop.web_events VALUES ('evt-014', 'user-04', 'click', '/blog/post-5', TIMESTAMP '2026-09-24 10:55:00 UTC', 'US');
INSERT INTO iceberg.shop.web_events VALUES ('evt-015', 'user-10', 'purchase', '/checkout', TIMESTAMP '2026-09-24 11:15:00 UTC', 'AU');
INSERT INTO iceberg.shop.web_events VALUES ('evt-016', 'user-05', 'page_view', '/pricing', TIMESTAMP '2026-09-24 12:30:00 UTC', 'FR');
INSERT INTO iceberg.shop.web_events VALUES ('evt-017', 'user-06', 'click', '/docs/api', TIMESTAMP '2026-09-24 13:45:00 UTC', 'JP');
INSERT INTO iceberg.shop.web_events VALUES ('evt-018', 'user-02', 'page_view', '/home', TIMESTAMP '2026-09-24 14:00:00 UTC', 'UK');
INSERT INTO iceberg.shop.web_events VALUES ('evt-019', 'user-07', 'purchase', '/checkout', TIMESTAMP '2026-09-24 15:20:00 UTC', 'IN');
INSERT INTO iceberg.shop.web_events VALUES ('evt-020', 'user-08', 'click', '/products/7', TIMESTAMP '2026-09-24 16:35:00 UTC', 'BR');

-- Day 3: 2026-09-25 — 10 events
INSERT INTO iceberg.shop.web_events VALUES ('evt-021', 'user-01', 'click', '/products/13', TIMESTAMP '2026-09-25 06:00:00 UTC', 'US');
INSERT INTO iceberg.shop.web_events VALUES ('evt-022', 'user-09', 'page_view', '/blog', TIMESTAMP '2026-09-25 07:15:00 UTC', 'CA');
INSERT INTO iceberg.shop.web_events VALUES ('evt-023', 'user-03', 'purchase', '/checkout', TIMESTAMP '2026-09-25 08:30:00 UTC', 'DE');
INSERT INTO iceberg.shop.web_events VALUES ('evt-024', 'user-10', 'page_view', '/about', TIMESTAMP '2026-09-25 09:45:00 UTC', 'AU');
INSERT INTO iceberg.shop.web_events VALUES ('evt-025', 'user-04', 'click', '/home', TIMESTAMP '2026-09-25 10:00:00 UTC', 'US');
INSERT INTO iceberg.shop.web_events VALUES ('evt-026', 'user-05', 'page_view', '/docs', TIMESTAMP '2026-09-25 11:15:00 UTC', 'FR');
INSERT INTO iceberg.shop.web_events VALUES ('evt-027', 'user-06', 'purchase', '/checkout', TIMESTAMP '2026-09-25 12:30:00 UTC', 'JP');
INSERT INTO iceberg.shop.web_events VALUES ('evt-028', 'user-07', 'click', '/products/55', TIMESTAMP '2026-09-25 13:45:00 UTC', 'IN');
INSERT INTO iceberg.shop.web_events VALUES ('evt-029', 'user-02', 'page_view', '/pricing', TIMESTAMP '2026-09-25 14:00:00 UTC', 'UK');
INSERT INTO iceberg.shop.web_events VALUES ('evt-030', 'user-08', 'page_view', '/home', TIMESTAMP '2026-09-25 15:15:00 UTC', 'BR');
```

### Step 3: Inspect Partition Metadata

```sql
SELECT * FROM iceberg.shop."web_events$partitions";
```

You should see partitions organized by `day(event_time)` and `bucket(user_id)`. Note that these partition columns do not appear in the table schema — they are hidden.

```sql
-- Also check the data files to see how they map to partitions
SELECT file_path, record_count, file_size_in_bytes
FROM iceberg.shop."web_events$files";
```

### Step 4: Demonstrate Partition Pruning (Filtered Query)

Run a query that filters on `event_time` — Iceberg will automatically prune partitions:

```sql
EXPLAIN ANALYZE
SELECT event_id, user_id, event_type, page, event_time
FROM iceberg.shop.web_events
WHERE event_time > TIMESTAMP '2026-09-24 00:00:00 UTC';
```

Look at the output — note the number of files/splits scanned. Only partitions for 2026-09-24 and 2026-09-25 should be read.

### Step 5: Full Table Scan (No Filter)

Now run the same query without any filter:

```sql
EXPLAIN ANALYZE
SELECT event_id, user_id, event_type, page, event_time
FROM iceberg.shop.web_events;
```

This scans **all** partitions across all 3 days.

### Step 6: Compare Filtered vs Full Scan

```
                          Filtered Scan         Full Scan
                          ─────────────         ─────────
  WHERE clause:           event_time > Sep 24   (none)
  Partitions scanned:     Sep 24 + Sep 25       Sep 23 + Sep 24 + Sep 25
  Files opened:           ~20                   ~30
  Rows processed:         20                    30
```

The filtered query skips the entire Sep 23 partition — a 33% reduction in I/O.

### Step 7: The "Hidden" Aspect

Look at what the user wrote:

```sql
WHERE event_time > TIMESTAMP '2026-09-24 00:00:00 UTC'
```

The user never mentioned a partition column. They never wrote `WHERE event_time_day = ...` or referenced any partition directory. Iceberg translated `event_time > '2026-09-24'` into `day(event_time) >= 2026-09-24` internally.

This is the core benefit: **users write business queries, Iceberg handles partition pruning transparently.**

In Hive-style partitioning, you would need:
- An explicit `event_date` column in the schema
- `WHERE event_date = '2026-09-24'` in every query
- Manual ETL to populate the partition column
- A full rewrite to change the partitioning scheme

---

## Part B: Partition Evolution

### Step 8: Evolve Partitioning (Day to Hour)

Your traffic grew and day-level partitions are too coarse. Evolve to hour-level partitioning **without rewriting any existing data**:

```sql
ALTER TABLE iceberg.shop.web_events
  SET PROPERTIES partitioning = ARRAY['hour(event_time)', 'bucket(4, user_id)'];
```

Verify the change:

```sql
SHOW CREATE TABLE iceberg.shop.web_events;
```

### Step 9: Insert New Data (Uses Hour-Level Partitions)

```sql
-- These new rows will be partitioned by hour, not day
INSERT INTO iceberg.shop.web_events VALUES ('evt-031', 'user-01', 'click', '/new-feature', TIMESTAMP '2026-09-25 18:05:00 UTC', 'US');
INSERT INTO iceberg.shop.web_events VALUES ('evt-032', 'user-02', 'page_view', '/new-feature', TIMESTAMP '2026-09-25 18:10:00 UTC', 'UK');
INSERT INTO iceberg.shop.web_events VALUES ('evt-033', 'user-03', 'click', '/new-feature', TIMESTAMP '2026-09-25 19:20:00 UTC', 'DE');
INSERT INTO iceberg.shop.web_events VALUES ('evt-034', 'user-04', 'purchase', '/checkout', TIMESTAMP '2026-09-25 19:35:00 UTC', 'US');
INSERT INTO iceberg.shop.web_events VALUES ('evt-035', 'user-05', 'page_view', '/home', TIMESTAMP '2026-09-25 20:45:00 UTC', 'FR');
```

### Step 10: Verify Coexistence of Old and New Partition Layouts

```sql
SELECT * FROM iceberg.shop."web_events$partitions";
```

You should see:
- **Old data** — partitioned by `day(event_time)` (2026-09-23, 2026-09-24, 2026-09-25)
- **New data** — partitioned by `hour(event_time)` (2026-09-25-18, 2026-09-25-19, 2026-09-25-20)

Both layouts coexist in the same table. Iceberg reads both correctly, applying the right partition spec for each data file. **No data was rewritten.**

```sql
-- Queries still work seamlessly across both layouts
SELECT
  CAST(event_time AS DATE) AS event_day,
  count(*) AS events
FROM iceberg.shop.web_events
GROUP BY CAST(event_time AS DATE)
ORDER BY event_day;
```

### Step 11: Compare truncate() and bucket() Transforms

Create a table that uses `truncate()` instead of `bucket()`:

```sql
CREATE TABLE iceberg.shop.web_events_truncated (
  event_id VARCHAR,
  user_id VARCHAR,
  event_type VARCHAR,
  page VARCHAR,
  event_time TIMESTAMP(6) WITH TIME ZONE,
  country VARCHAR
)
WITH (
  partitioning = ARRAY['month(event_time)', 'truncate(2, country)']
);
```

```sql
INSERT INTO iceberg.shop.web_events_truncated VALUES ('evt-t01', 'user-01', 'click', '/home', TIMESTAMP '2026-09-25 10:00:00 UTC', 'US');
INSERT INTO iceberg.shop.web_events_truncated VALUES ('evt-t02', 'user-02', 'page_view', '/docs', TIMESTAMP '2026-09-25 11:00:00 UTC', 'UK');
INSERT INTO iceberg.shop.web_events_truncated VALUES ('evt-t03', 'user-03', 'click', '/home', TIMESTAMP '2026-09-25 12:00:00 UTC', 'DE');
INSERT INTO iceberg.shop.web_events_truncated VALUES ('evt-t04', 'user-04', 'purchase', '/checkout', TIMESTAMP '2026-09-25 13:00:00 UTC', 'US');
```

```sql
SELECT * FROM iceberg.shop."web_events_truncated$partitions";
```

Compare the two approaches:

```
Transform         How It Works                       Best For
───────────────  ──────────────────────────────────  ─────────────────────────
bucket(N, col)    Hash value into N buckets           Even distribution, high-cardinality columns
                  "user-01" → bucket 2                (user IDs, UUIDs, session IDs)
                  Bucket number is opaque

truncate(N, col)  Keep first N characters/digits      Range-scannable, predictable grouping
                  "US" → "US", "UK" → "UK"            (country codes, zip prefixes, SKU prefixes)
                  Value is human-readable
```

`bucket()` is best when you want even distribution regardless of data skew. `truncate()` is best when you want human-readable partitions and range-based queries on the truncated column.

---

## Exercises

1. **Month-based partitioning** — Create a table `iceberg.shop.monthly_events` with `partitioning = ARRAY['month(event_time)', 'bucket(8, user_id)']`. Insert 20 rows across 3 different months. Query with `WHERE event_time > TIMESTAMP '2026-08-01 00:00:00 UTC'` and check `EXPLAIN ANALYZE` to confirm partition pruning.

2. **Pruning comparison** — Using `web_events`, run `EXPLAIN ANALYZE` for each query and record the number of files scanned:
   - `WHERE event_time > TIMESTAMP '2026-09-24 00:00:00 UTC'`
   - `WHERE event_time > TIMESTAMP '2026-09-23 00:00:00 UTC'`
   - No filter at all
   How do the file counts compare?

3. **Evolution chain** — Evolve `web_events` from `hour(event_time)` to `month(event_time)`. Insert 5 more rows. Verify that the table now has three partition spec generations (day, hour, month) coexisting.

4. **Bucket count tuning** — Create two tables with identical data: one with `bucket(4, user_id)` and one with `bucket(16, user_id)`. Insert 50 rows into each. Compare the partition metadata. When would you choose more buckets vs fewer?

5. **Challenge: Partition health report** — Write a query that joins `"web_events$partitions"` with `"web_events$files"` to show per-partition file counts and total sizes. Identify any partitions that would benefit from compaction (too many small files).

**Congratulations!** You've mastered Iceberg's hidden partitioning transforms, demonstrated automatic partition pruning, and evolved partition specs without a single data rewrite — all coordinated through Polaris.
