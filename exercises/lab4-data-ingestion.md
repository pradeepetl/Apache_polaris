# Lab 4 — Data Ingestion

**Level:** 4 (Advanced) | **Time:** 30 minutes

**Goal:** Ingest data into Iceberg tables from multiple engines — dlt (Python) and Spark — then query from Trino. Understand multi-engine interoperability through Polaris.

---

## Concepts

Polaris acts as the **single source of truth** for Iceberg metadata. Multiple engines can read and write to the same tables because they all go through the same REST catalog:

```
dlt (Python) ──► Polaris REST Catalog ◄── Spark
                        │
                   LocalStack S3
                        │
                  Trino reads data
```

This is the key value of an open catalog: **no vendor lock-in, any engine can participate**.

## Part A: dlt Earthquake Pipeline

### Step 1: Check the Pipeline Output

The `dlt-earthquakes` container ran automatically on startup. Check its logs:

```bash
docker logs dlt-earthquakes
```

You should see something like:
```
dlt Earthquake Ingestion Pipeline
Fetching earthquakes from USGS...
Got 259 earthquake events
Pipeline load complete!
```

### Step 2: Query Earthquake Data in Trino

```bash
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure
```

```sql
-- Total earthquakes loaded
SELECT count(*) FROM iceberg.earthquakes.events;

-- Strongest earthquakes
SELECT magnitude, place, event_time, depth_km
FROM iceberg.earthquakes.events
ORDER BY magnitude DESC LIMIT 10;

-- Earthquakes by region
SELECT
  CASE
    WHEN longitude < -30 THEN 'Americas'
    WHEN longitude < 60 THEN 'Europe/Africa'
    ELSE 'Asia/Pacific'
  END AS region,
  count(*) AS quakes,
  round(avg(magnitude), 2) AS avg_mag,
  round(max(magnitude), 2) AS max_mag
FROM iceberg.earthquakes.events
GROUP BY 1 ORDER BY 2 DESC;
```

### Step 3: Re-Run the Pipeline (Append Mode)

```bash
docker restart dlt-earthquakes
docker logs -f dlt-earthquakes
```

Wait for it to finish, then:

```sql
SELECT count(*) FROM iceberg.earthquakes.events;
```

The count should roughly double — dlt uses `append` mode, so each run adds the latest batch.

### Step 4: Understand the Pipeline Code

Look at the pipeline source:

```bash
cat dlt/pipeline.py
```

Key points:
- `@dlt.resource(write_disposition="append", table_format="iceberg")` — tells dlt to write as Iceberg
- `destination="filesystem"` — writes Parquet files to S3
- `register_in_polaris()` — registers the Iceberg table metadata in Polaris so Trino/Spark can find it
- Data is transformed from GeoJSON to flat rows during `yield`

## Part B: Write Data from Spark

### Step 5: Open Jupyter Notebook

Go to http://localhost:8888?token=spark123

Create a new Python 3 notebook (or open an existing one in the `work/` folder).

### Step 6: Write a New Table from Spark

In a notebook cell:

```python
# Check existing data
spark.sql("SELECT count(*) FROM polaris.shop.orders").show()
```

```python
# Create a new table from Spark
spark.sql("""
  CREATE TABLE IF NOT EXISTS polaris.shop.daily_summary (
    order_date DATE,
    num_orders INT,
    total_revenue DOUBLE
  )
""")
```

```python
# Insert aggregated data
spark.sql("""
  INSERT INTO polaris.shop.daily_summary
  SELECT
    CAST(order_date AS DATE),
    COUNT(*) AS num_orders,
    SUM(total_amount) AS total_revenue
  FROM polaris.shop.orders
  GROUP BY CAST(order_date AS DATE)
""")
```

```python
# Verify
spark.sql("SELECT * FROM polaris.shop.daily_summary ORDER BY order_date").show()
```

### Step 7: Read Spark-Written Data from Trino

Back in the Trino CLI:

```sql
-- Trino can immediately see what Spark wrote
SELECT * FROM iceberg.shop.daily_summary ORDER BY order_date;
```

This works because both Spark and Trino use Polaris as the catalog — Spark writes the metadata, and Trino reads it instantly.

### Step 8: Cross-Engine Federation

Combine Spark-written data (Iceberg) with Postgres data in Trino:

```sql
SELECT
  ds.order_date,
  ds.num_orders,
  round(ds.total_revenue, 2) AS revenue,
  (SELECT count(DISTINCT country)
   FROM postgres.public.customers) AS total_countries
FROM iceberg.shop.daily_summary ds
ORDER BY ds.order_date;
```

## Part C: Query Earthquake Data from Spark

### Step 9: Read dlt-Written Data from Spark

In Jupyter:

```python
spark.sql("""
  SELECT magnitude, place, event_time
  FROM polaris.earthquakes.events
  WHERE magnitude > 4
  ORDER BY magnitude DESC
""").show(20, truncate=False)
```

dlt wrote the data, Polaris cataloged it, and Spark reads it — three different tools, zero data movement.

---

## Exercises

1. **Modify the earthquake query** to find all earthquakes with `tsunami = true`. How many are there?
2. **Create a Spark table** called `polaris.earthquakes.magnitude_bins` with columns `bin` (string) and `count` (int). Populate it with magnitude ranges: `<2`, `2-3`, `3-4`, `4-5`, `5+`.
3. **Query `magnitude_bins` from Trino** to verify cross-engine visibility.
4. **Use `DESCRIBE`** in Trino to compare the schema of a dlt-created table vs a Spark-created table. Any differences?
5. **Challenge:** Write a Python script (outside of dlt) that uses `requests` to fetch weather data from a public API and inserts it into a new Iceberg table via Spark SQL.

**Next:** [Lab 5 — API Mastery](lab5-api-mastery.md)
