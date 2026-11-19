# Lab 12 — Schema Evolution

**Level:** 4 (Advanced) | **Time:** 25 minutes

**Goal:** Add, drop, rename, and reorder columns in Iceberg tables without rewriting data. Demonstrate type promotion and backward compatibility.

---

## Concepts

Iceberg tracks every column by an internal **column ID**, not by name or position. This makes schema changes safe, cheap, and non-breaking:

```
Key Principle                          Why It Matters
────────────────────────────────────  ─────────────────────────────────────────────────
Column IDs (not names/positions)       Renames and reorders never break existing data
Old files readable after changes       New columns are null-filled on read
Type promotion (int→bigint, etc.)      Widen types without rewriting Parquet files
Metadata-only operations               No data rewrite — instant ALTER TABLE
Full schema history                    Every version is recorded and queryable
```

**How old data files work with a new schema:**

```
Schema v1 (columns by ID)          Schema v3 (after evolution)
┌──────────────────────────┐       ┌──────────────────────────┐
│ ID=1  user_id   INT      │       │ ID=1  user_id   INT      │
│ ID=2  name      VARCHAR  │  ──>  │ ID=2  full_name VARCHAR  │  (renamed, same ID)
│ ID=3  email     VARCHAR  │       │ ID=3  (dropped)          │  (column removed)
│ ID=4  signup_date DATE   │       │ ID=4  signup_date DATE   │
└──────────────────────────┘       │ ID=5  age       BIGINT   │  (added, null in old files)
                                   │ ID=6  country   VARCHAR  │  (added, null in old files)
   Old Parquet files still          └──────────────────────────┘
   contain IDs 1-4.
   Iceberg maps them to the            Reads from old files:
   current schema by ID,               - ID=2 → full_name (rename is transparent)
   filling NULLs for ID=5,6.           - ID=3 → skipped (column dropped)
                                        - ID=5,6 → NULL (not in old file)
```

**Key point:** Polaris stores the schema metadata. Every engine (Trino, Spark, PyIceberg) sees the same evolved schema instantly — no coordination needed.

---

## Part A: Build and Evolve a Schema

### Step 1: Create the User Profiles Table

Connect as admin:

```bash
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure
```

```sql
CREATE TABLE iceberg.shop.user_profiles (
  user_id INT,
  name VARCHAR,
  email VARCHAR,
  signup_date DATE
);
```

### Step 2: Insert Sample Data

```sql
INSERT INTO iceberg.shop.user_profiles VALUES
  (1, 'Alice Johnson', 'alice@example.com', DATE '2024-01-15'),
  (2, 'Bob Smith', 'bob@example.com', DATE '2024-02-20'),
  (3, 'Carol White', 'carol@example.com', DATE '2024-03-10'),
  (4, 'David Brown', 'david@example.com', DATE '2024-04-05'),
  (5, 'Eve Davis', 'eve@example.com', DATE '2024-05-12'),
  (6, 'Frank Miller', 'frank@example.com', DATE '2024-06-18'),
  (7, 'Grace Wilson', 'grace@example.com', DATE '2024-07-22'),
  (8, 'Henry Taylor', 'henry@example.com', DATE '2024-08-30'),
  (9, 'Iris Anderson', 'iris@example.com', DATE '2024-09-14'),
  (10, 'Jack Thomas', 'jack@example.com', DATE '2024-10-01');
```

### Step 3: Show Current Schema

```sql
DESCRIBE iceberg.shop.user_profiles;
```

You should see 4 columns: `user_id`, `name`, `email`, `signup_date`.

---

## Part B: Adding and Querying New Columns

### Step 4: Add Columns

```sql
ALTER TABLE iceberg.shop.user_profiles ADD COLUMN age INT;
ALTER TABLE iceberg.shop.user_profiles ADD COLUMN country VARCHAR;
```

### Step 5: Query — Old Rows Have NULLs for New Columns

```sql
SELECT * FROM iceberg.shop.user_profiles ORDER BY user_id;
```

**Observe:** All 10 existing rows show `NULL` for `age` and `country`. The original Parquet files were **not** rewritten — Iceberg fills NULLs on read.

### Step 6: Insert New Rows with All Columns

```sql
INSERT INTO iceberg.shop.user_profiles VALUES
  (11, 'Karen Lee', 'karen@example.com', DATE '2024-11-05', 29, 'USA'),
  (12, 'Leo Martinez', 'leo@example.com', DATE '2024-11-10', 34, 'Mexico'),
  (13, 'Mia Garcia', 'mia@example.com', DATE '2024-12-01', 27, 'Spain');
```

### Step 7: Query — Mixed Rows

```sql
SELECT user_id, name, age, country
FROM iceberg.shop.user_profiles
ORDER BY user_id;
```

**Observe:** Rows 1-10 have `NULL` for `age` and `country`. Rows 11-13 have values. Both old and new data files coexist seamlessly.

---

## Part C: Rename, Drop, and Type Promotion

### Step 8: Rename a Column

```sql
ALTER TABLE iceberg.shop.user_profiles RENAME COLUMN name TO full_name;
```

Verify:

```sql
DESCRIBE iceberg.shop.user_profiles;
```

The column is now `full_name`. Old data files still store it under the original internal column ID — the rename is purely a metadata change.

```sql
SELECT user_id, full_name FROM iceberg.shop.user_profiles WHERE user_id <= 3;
```

### Step 9: Drop a Column

```sql
ALTER TABLE iceberg.shop.user_profiles DROP COLUMN email;
```

Verify:

```sql
DESCRIBE iceberg.shop.user_profiles;
```

The `email` column is gone. The data still exists in old Parquet files but Iceberg simply skips that column ID on read.

```sql
SELECT * FROM iceberg.shop.user_profiles WHERE user_id <= 3;
```

### Step 10: Type Promotion

Widen `age` from INT to BIGINT — a safe promotion that does not require rewriting data:

```sql
ALTER TABLE iceberg.shop.user_profiles ALTER COLUMN age SET DATA TYPE BIGINT;
```

Verify:

```sql
DESCRIBE iceberg.shop.user_profiles;
```

The `age` column is now `bigint`. Existing INT values are read as BIGINT transparently.

**Supported type promotions in Iceberg:**
- `int` to `bigint`
- `float` to `double`
- `decimal(P, S)` to `decimal(P', S)` where P' > P (increase precision)

---

## Part D: Inspect Schema History with PyIceberg

### Step 11: View Schema History

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

table = catalog.load_table("shop.user_profiles")

# Current schema
print("Current schema:")
print(table.schema())
print()

# Schema history — Iceberg records every version
for schema in table.schemas().values():
    print(f"Schema ID {schema.schema_id}: {[f.name for f in schema.fields]}")
```

### Step 12: Time Travel — Query Old Snapshot

```sql
-- List all snapshots
SELECT snapshot_id, committed_at
FROM iceberg.shop."user_profiles$snapshots"
ORDER BY committed_at;
```

Use the **first** snapshot ID (from the original INSERT) to query the table as it was before any schema changes:

```sql
-- Replace <snapshot_id> with the first snapshot ID from above
SELECT * FROM iceberg.shop.user_profiles FOR VERSION AS OF <snapshot_id>;
```

**Observe:** The old snapshot returns the original 4-column schema — `user_id`, `name`, `email`, `signup_date`.

### Step 13: Verify Column ID Stability

```python
table = catalog.load_table("shop.user_profiles")

print("Column ID stability across renames:")
for field in table.schema().fields:
    print(f"  ID={field.field_id}  {field.name:15s}  {field.field_type}")

print()
print("Key insight: 'full_name' kept the same column ID as the original 'name'.")
print("That's why old Parquet files with 'name' are still readable — Iceberg")
print("matches by ID, not by name.")
```

---

## Exercises

1. **Add a nested column** — Add a column `address` of type `ROW(street VARCHAR, city VARCHAR, zip VARCHAR)`. Insert a row with address data and query it.

2. **Multiple renames** — Rename `full_name` to `display_name`, then back to `full_name`. Verify the column ID stays the same throughout.

3. **Schema impact on partitioning** — Add a `region` column, then set the table partitioning to include `region`. Insert rows with different regions and verify partition pruning with `EXPLAIN`.

4. **Type promotion chain** — Create a new table with a `score DECIMAL(5,2)` column. Insert data, promote to `DECIMAL(10,2)`, insert more data, and verify all rows are queryable.

5. **Challenge: Five-evolution verification** — Evolve the `user_profiles` schema 5 additional times (add columns, rename, drop, promote types). After each change, insert at least one row. Then write a PyIceberg script that loads every historical snapshot and verifies each one is still queryable by printing the row count and column names per snapshot.

**Congratulations!** You've performed safe, metadata-only schema evolution on Iceberg tables and verified backward compatibility across all historical snapshots.
