# Lab 15 — Branching & Tagging

**Level:** 5 (Advanced) | **Time:** 30 minutes

**Goal:** Use Iceberg's git-like branching and tagging to create named references to snapshots — tags for audit/compliance, branches for safe experimentation.

---

## Concepts

Iceberg tables maintain a **ref system** similar to git. Every table has a `main` branch by default, but you can create additional **tags** and **branches** that point to specific snapshots:

| Ref Type | Mutable? | Description | Analogy |
|----------|----------|-------------|---------|
| **Tag** | No (immutable pointer) | A named pointer to a specific snapshot | Git tag |
| **Branch** | Yes (receives new commits) | A named pointer that can advance independently | Git branch |

- **Tag**: Marks a point in time for auditing, compliance, or reproducibility. Once created, it always points to the same snapshot.
- **Branch**: Allows experimentation without affecting production readers. New writes to a branch do not change the main branch.

```
main:    [snap1] --> [snap2] --> [snap3] --> [snap4]
                       |            |
                       v            v
Tags:              audit-q3    pre-migration
                       |
Branch:               [snap2] --> [exp-snap1] --> [exp-snap2]
                      experiment branch (independent writes)
```

**Key point:** Tags protect snapshots from expiry — even if you run `expire_snapshots`, a tagged snapshot survives. Branches let you write safely to a table without impacting other readers or pipelines.

---

## Part A: Tags (Named Snapshots)

### Step 1: Create the Products Table

Connect as admin:

```bash
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure
```

```sql
CREATE TABLE iceberg.shop.products (
  product_id VARCHAR,
  name VARCHAR,
  category VARCHAR,
  price DECIMAL(10,2),
  in_stock BOOLEAN
);
```

### Step 2: Insert Initial Products

```sql
INSERT INTO iceberg.shop.products VALUES
  ('P001', 'Wireless Mouse',      'Peripherals', 29.99, true),
  ('P002', 'Mechanical Keyboard', 'Peripherals', 89.99, true),
  ('P003', 'USB-C Hub',           'Accessories', 45.00, true),
  ('P004', 'Monitor Stand',       'Furniture',   64.50, true),
  ('P005', 'Webcam HD',           'Peripherals', 79.99, true),
  ('P006', 'Desk Lamp',           'Furniture',   34.99, false),
  ('P007', 'Cable Organizer',     'Accessories', 12.99, true),
  ('P008', 'Laptop Cooling Pad',  'Accessories', 27.50, true);
```

### Step 3: Create a Tag — `audit_q3_2026`

First, find the current snapshot ID:

```sql
SELECT snapshot_id, operation, committed_at
FROM iceberg.shop."products$snapshots"
ORDER BY committed_at;
```

Note the `snapshot_id` from the INSERT. Now create a tag that points to it:

```sql
-- Replace <snapshot_id> with your actual snapshot ID
ALTER TABLE iceberg.shop.products
SET PROPERTIES
  "refs.audit_q3_2026.type" = 'TAG',
  "refs.audit_q3_2026.snapshot-id" = '<snapshot_id>';
```

The tag `audit_q3_2026` now permanently points to the snapshot containing the original 8 products at their original prices.

### Step 4: Make Changes (New Snapshot)

Simulate a price hike and add a new product:

```sql
UPDATE iceberg.shop.products
SET price = price * 1.15
WHERE category = 'Peripherals';
```

```sql
INSERT INTO iceberg.shop.products VALUES
  ('P009', 'Noise-Cancelling Headphones', 'Peripherals', 199.99, true);
```

### Step 5: Query the Tagged Version

The tag still points to the original snapshot. Query it to confirm immutability:

```sql
-- Replace <tag_snapshot_id> with the snapshot ID you tagged in Step 3
SELECT *
FROM iceberg.shop.products
FOR VERSION AS OF <tag_snapshot_id>
ORDER BY product_id;
```

You should see all 8 original products at their original prices. No price hike, no P009.

### Step 6: Compare Current State vs Tagged State

```sql
-- Replace <tag_snapshot_id> with the snapshot ID from Step 3
SELECT
  COALESCE(c.product_id, t.product_id) AS product_id,
  COALESCE(c.name, t.name) AS name,
  t.price AS tagged_price,
  c.price AS current_price,
  CASE
    WHEN c.product_id IS NULL THEN 'DELETED'
    WHEN t.product_id IS NULL THEN 'ADDED'
    WHEN c.price <> t.price THEN 'PRICE CHANGED'
    ELSE 'UNCHANGED'
  END AS status
FROM iceberg.shop.products c
FULL OUTER JOIN iceberg.shop.products FOR VERSION AS OF <tag_snapshot_id> t
  ON c.product_id = t.product_id
ORDER BY COALESCE(c.product_id, t.product_id);
```

Expected output:

| product_id | name | tagged_price | current_price | status |
|------------|------|-------------|---------------|--------|
| P001 | Wireless Mouse | 29.99 | 34.49 | PRICE CHANGED |
| P002 | Mechanical Keyboard | 89.99 | 103.49 | PRICE CHANGED |
| P005 | Webcam HD | 79.99 | 91.99 | PRICE CHANGED |
| P009 | Noise-Cancelling Headphones | NULL | 199.99 | ADDED |
| ... | ... | ... | ... | UNCHANGED |

---

## Part B: Branches (Independent Write Paths)

### Step 7: Create a Branch — `experiment`

Get the current snapshot ID:

```sql
SELECT snapshot_id, operation, committed_at
FROM iceberg.shop."products$snapshots"
ORDER BY committed_at DESC
LIMIT 1;
```

Create the branch:

```sql
-- Replace <snapshot_id> with the latest snapshot ID
ALTER TABLE iceberg.shop.products
SET PROPERTIES
  "refs.experiment.type" = 'BRANCH',
  "refs.experiment.snapshot-id" = '<snapshot_id>';
```

The branch `experiment` now starts from the same snapshot as the current main branch.

### Step 8: Write to the Experiment Branch

In Trino, direct writes to a named branch require setting the session property or using a branch-aware catalog configuration. If your Trino version supports it:

```sql
-- Some Trino versions support branch-aware writes via table properties
-- If not supported directly, use PyIceberg (shown in Part D)
```

For the conceptual understanding: writes to the `experiment` branch would create new snapshots that are only visible when reading from that branch, leaving `main` unchanged.

### Step 9: Query the Main Branch

The main branch is unaffected by any writes to the experiment branch:

```sql
SELECT COUNT(*) AS main_count, ROUND(AVG(price), 2) AS main_avg_price
FROM iceberg.shop.products;
```

### Step 10: Query the Experiment Branch

To read from the experiment branch, use the snapshot ID that the branch points to:

```sql
-- Replace <experiment_snapshot_id> with the branch's snapshot ID
SELECT COUNT(*) AS exp_count, ROUND(AVG(price), 2) AS exp_avg_price
FROM iceberg.shop.products
FOR VERSION AS OF <experiment_snapshot_id>;
```

If writes were made to the experiment branch, the row counts and averages would differ from main.

---

## Part C: Use Cases

### Step 11: When to Use Tags vs Branches

```
Feature    Tag                          Branch
---------  ---------------------------  ------------------------------
Mutable?   No (immutable pointer)       Yes (receives new commits)
Use case   Audit, compliance, releases  Experimentation, staging
Analogy    Git tag                      Git branch
Example    "Q3-2026 audit snapshot"     "test new ETL before promoting"
```

**Tags** are ideal for:
- Regulatory/compliance snapshots ("this is what the data looked like on audit date")
- Release markers ("this version was used for the Q3 report")
- Reproducibility ("re-run my analysis against this exact data")
- Protecting snapshots from garbage collection (`expire_snapshots` will not remove a tagged snapshot)

**Branches** are ideal for:
- Testing ETL changes without impacting production reads
- A/B testing data transformations
- Staging new data before promoting to main
- Allowing data scientists to experiment in isolation

---

## Part D: Verify with PyIceberg

### Step 12: Inspect Refs (Tags and Branches)

Use PyIceberg to programmatically inspect all refs on the table:

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

table = catalog.load_table("shop.products")

# View snapshot history
print("Snapshot history:")
for snapshot in table.history():
    print(f"  snapshot_id={snapshot.snapshot_id}  timestamp={snapshot.timestamp_ms}")

# View metadata — refs are stored in table metadata
print("\nTable metadata refs:")
metadata = table.metadata
if hasattr(metadata, 'refs'):
    for ref_name, ref in metadata.refs.items():
        print(f"  {ref_name}: type={ref.snapshot_ref_type}, snapshot_id={ref.snapshot_id}")
```

---

## Exercises

1. **Create a second tag** — Create a tag `pre_price_hike` before updating prices. After the update, compare prices between the two tags using `FULL OUTER JOIN` on two versioned references.

2. **Branch isolation test** — Create a branch, write 100 rows to it (via PyIceberg if Trino branch writes are not available), then query both main and branch to verify isolation.

3. **Tags protect snapshots** — Tag a snapshot, then expire old snapshots with `CALL iceberg.system.expire_snapshots(...)`. Does the tagged snapshot survive expiration? (It should — tags protect snapshots from expiry.)

4. **Discussion: A/B testing** — How would you use branches for A/B testing data transformations? Sketch a workflow where two branches receive different transformations, both are validated, and the better one is promoted to main.

5. **Challenge: Promote branch** — Build a "promote branch" workflow: write to a branch, validate the data (row counts, null checks, aggregation sanity checks), then fast-forward main to the branch's latest snapshot using `CALL iceberg.system.fast_forward(...)` or by updating the main ref.

**Congratulations!** You can now create named references to Iceberg snapshots — immutable tags for audit and compliance, mutable branches for safe experimentation — all managed through Polaris as the central catalog.
