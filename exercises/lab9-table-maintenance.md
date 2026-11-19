# Lab 9 — Iceberg Table Maintenance

**Level:** 5 (Advanced) | **Time:** 40 minutes

**Goal:** See firsthand why table maintenance matters. Create a real performance problem with small files, measure the impact, fix it with compaction, and learn the full maintenance toolkit.

---

## Concepts

Iceberg tables accumulate overhead over time:

```
Problem                     Solution                    Trino Command
─────────────────────────  ─────────────────────────── ──────────────────────────────
Many small files            Compaction (rewrite files)  ALTER TABLE ... EXECUTE optimize
(slow reads, high S3 cost)

Old snapshots piling up     Expire snapshots            ALTER TABLE ... EXECUTE expire_snapshots
(metadata bloat)

Leftover data files         Remove orphan files         ALTER TABLE ... EXECUTE remove_orphan_files
(wasted storage)

Changing query patterns     Partition evolution          ALTER TABLE ... SET PROPERTIES
(scan too much data)
```

**Key point:** Polaris coordinates the metadata. You run maintenance from any engine (Trino, Spark), and the updated metadata is immediately visible to all other engines through the shared catalog.

---

## Part A: Why Maintenance Matters (Performance Demo)

In this section, we'll create a real performance problem and then fix it.

**The scenario:** An IoT pipeline sends sensor readings every few seconds. Each micro-batch creates a tiny Parquet file. After many inserts, the table has dozens of small files — each requiring a separate S3 GET request to read. Queries slow down.

### Step 1: Create the Sensor Table

Connect as admin:

```bash
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure
```

```sql
CREATE TABLE iceberg.shop.sensor_readings (
  sensor_id VARCHAR,
  temperature DOUBLE,
  humidity DOUBLE,
  reading_time TIMESTAMP(6) WITH TIME ZONE
);
```

### Step 2: Simulate Micro-Batch Writes (20 Small Inserts)

Each INSERT creates a new data file and a new snapshot — simulating a streaming pipeline:

```sql
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-01', 22.5, 45.0, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-02', 23.1, 42.3, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-03', 21.8, 48.7, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-01', 22.7, 44.5, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-02', 23.4, 41.9, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-03', 21.5, 49.2, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-01', 22.9, 43.8, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-02', 23.8, 40.5, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-03', 21.2, 50.1, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-01', 23.0, 44.0, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-02', 24.1, 39.8, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-03', 20.9, 51.3, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-01', 23.2, 43.2, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-02', 24.5, 38.7, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-03', 20.6, 52.0, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-01', 23.5, 42.5, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-02', 24.8, 37.9, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-03', 20.3, 53.1, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-01', 23.8, 41.8, CURRENT_TIMESTAMP);
INSERT INTO iceberg.shop.sensor_readings VALUES ('sensor-02', 25.0, 37.0, CURRENT_TIMESTAMP);
```

### Step 3: Observe the Damage

```sql
-- How many data files?
SELECT count(*) AS file_count FROM iceberg.shop."sensor_readings$files";

-- How many snapshots?
SELECT count(*) AS snapshot_count FROM iceberg.shop."sensor_readings$snapshots";

-- How many manifest files?
SELECT count(*) AS manifest_count FROM iceberg.shop."sensor_readings$manifests";
```

Expected: **20 data files, 20 snapshots, 20+ manifests** — for just 20 rows of data!

```sql
-- Look at the individual file sizes
SELECT file_path, file_format, record_count, file_size_in_bytes
FROM iceberg.shop."sensor_readings$files";
```

**Question:** Each file holds just 1 row. What's the overhead? How much of each file is metadata vs actual data?

### Step 4: Benchmark Query BEFORE Compaction

```sql
-- Time this query
SELECT
  sensor_id,
  count(*) AS readings,
  round(avg(temperature), 2) AS avg_temp,
  round(avg(humidity), 2) AS avg_humidity,
  min(reading_time) AS first_reading,
  max(reading_time) AS last_reading
FROM iceberg.shop.sensor_readings
GROUP BY sensor_id
ORDER BY sensor_id;
```

Note the query time shown in Trino (or check the Trino Web UI at http://localhost:8080 for detailed timing).

Also check the query plan:

```sql
EXPLAIN ANALYZE
SELECT sensor_id, avg(temperature) AS avg_temp
FROM iceberg.shop.sensor_readings
GROUP BY sensor_id;
```

Look for `Input: 20 rows` across multiple splits — Trino opens 20 separate files.

### Step 5: Run Compaction

```sql
ALTER TABLE iceberg.shop.sensor_readings EXECUTE optimize;
```

### Step 6: Observe the Fix

```sql
-- File count after compaction
SELECT count(*) AS file_count FROM iceberg.shop."sensor_readings$files";

-- Snapshot count (one more added for the compaction)
SELECT count(*) AS snapshot_count FROM iceberg.shop."sensor_readings$snapshots";

-- Check the compacted file
SELECT file_path, file_format, record_count, file_size_in_bytes
FROM iceberg.shop."sensor_readings$files";
```

Expected: **1-2 data files** containing all 20 rows, instead of 20 tiny files.

### Step 7: Benchmark Query AFTER Compaction

Run the exact same query again:

```sql
SELECT
  sensor_id,
  count(*) AS readings,
  round(avg(temperature), 2) AS avg_temp,
  round(avg(humidity), 2) AS avg_humidity,
  min(reading_time) AS first_reading,
  max(reading_time) AS last_reading
FROM iceberg.shop.sensor_readings
GROUP BY sensor_id
ORDER BY sensor_id;
```

Compare the query time. Check the Trino Web UI — the query now reads from 1 file instead of 20.

```sql
EXPLAIN ANALYZE
SELECT sensor_id, avg(temperature) AS avg_temp
FROM iceberg.shop.sensor_readings
GROUP BY sensor_id;
```

Look for the difference: fewer splits, fewer files opened.

### Step 8: The Impact Summary

```
                    BEFORE          AFTER
                    ──────          ─────
Data files:         20              1-2
Snapshots:          20              21 (compaction adds one)
File opens/query:   20 S3 GETs      1-2 S3 GETs
Row distribution:   1 row/file      20 rows/file
```

**At scale:** Imagine 10,000 micro-batches per day. After a month, that's 300,000 tiny files. Every query must open all of them. Without compaction, queries that should take seconds take minutes.

---

## Part B: Full Maintenance Toolkit

Now that you've seen why maintenance matters, let's go through the complete toolkit.

### Step 9: Expire Old Snapshots

Our sensor table has 21 snapshots (20 inserts + 1 compaction). The old pre-compaction snapshots are useless — they point to files that were rewritten.

```sql
SELECT count(*) AS snapshot_count FROM iceberg.shop."sensor_readings$snapshots";

-- Expire snapshots older than 1 minute
ALTER TABLE iceberg.shop.sensor_readings EXECUTE expire_snapshots(retention_threshold => '1m');

SELECT count(*) AS snapshot_count FROM iceberg.shop."sensor_readings$snapshots";
```

**Question:** How many snapshots remain? Why does Iceberg keep at least one?

### Step 10: Remove Orphan Files

The 20 original tiny files are still on S3 — they're now "orphans" (no snapshot references them).

```sql
ALTER TABLE iceberg.shop.sensor_readings EXECUTE remove_orphan_files(retention_threshold => '1m');
```

This cleans up wasted S3 storage.

### Step 11: Partition Evolution

Add time-based partitioning so future reads can skip irrelevant data:

```sql
ALTER TABLE iceberg.shop.sensor_readings
  SET PROPERTIES partitioning = ARRAY['day(reading_time)'];
```

Verify:

```sql
SHOW CREATE TABLE iceberg.shop.sensor_readings;
```

New inserts will be organized by day. Old data keeps its original layout — no rewrite needed.

### Step 12: Verify Across Engines

Verify with PyIceberg that all maintenance changes are visible:

```python
from pyiceberg.catalog import load_catalog

catalog = load_catalog("polaris", **{
    "type": "rest",
    "uri": "http://polaris:8181/api/catalog",
    "warehouse": "polaris_warehouse",
    "credential": "root:s3cr3t",
    "scope": "PRINCIPAL_ROLE:ALL",
    "header.Polaris-Realm": "POLARIS",
    "py-io-impl": "pyiceberg.io.fsspec.FsspecFileIO",
    "s3.endpoint": "http://localstack:4566",
    "s3.access-key-id": "test",
    "s3.secret-access-key": "test",
    "s3.path-style-access": "true",
})

table = catalog.load_table("shop.sensor_readings")
print(f"Snapshots: {len(table.history())}")
print(f"Partition spec: {table.spec()}")
```

Trino did the maintenance, Polaris stored the metadata, PyIceberg sees it instantly.

---

## Exercises

1. **Scale the test** — Insert 50 more rows (one at a time) into `sensor_readings`, then compare query time before and after `optimize`.

2. **Run the full cycle** on `earthquakes.events` — optimize → expire → orphan removal. Report the before/after metrics.

3. **Compare `EXPLAIN ANALYZE`** output before and after compaction. How many "splits" does Trino process in each case?

4. **Test partition pruning** — After adding day-based partitioning, insert rows for 3 different days. Then `EXPLAIN` a query with `WHERE reading_time > TIMESTAMP '...'` and confirm partition pruning appears.

5. **Challenge:** Write a Python function that takes a table name and returns a maintenance recommendation: "COMPACT" if file_count > 10, "EXPIRE" if snapshot_count > 5, "CLEAN" if appropriate, or "HEALTHY" if everything looks good.

**Congratulations!** You've seen firsthand how small file accumulation degrades performance and how Iceberg's maintenance operations fix it — all coordinated through Polaris.
