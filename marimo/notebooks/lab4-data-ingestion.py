import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 4 — Data Ingestion")


@app.cell(hide_code=True)
def _():
    import os
    from datetime import datetime, timedelta, timezone

    import marimo as mo
    import pandas as pd
    import pyarrow as pa
    import requests
    import urllib3
    from pyiceberg.catalog import load_catalog
    from sqlalchemy import create_engine, text

    urllib3.disable_warnings()

    TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
    POLARIS_HOST = os.environ.get("POLARIS_HOST", "localhost")
    POLARIS = f"http://{POLARIS_HOST}:8181"
    POLARIS_HEALTH = f"http://{POLARIS_HOST}:8182/q/health"
    TRINO_INFO = f"https://{TRINO_HOST}:8443/v1/info"
    S3_ENDPOINT = f"http://{os.environ.get('S3_HOST', 'localhost')}:4566"
    CATALOG_NAME = "polaris_warehouse"

    trino = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (
        CATALOG_NAME,
        POLARIS,
        POLARIS_HEALTH,
        S3_ENDPOINT,
        TRINO_INFO,
        datetime,
        load_catalog,
        mo,
        pa,
        pd,
        requests,
        text,
        timedelta,
        timezone,
        trino,
    )


@app.cell(hide_code=True)
def _(datetime, mo, pd, text, timedelta, timezone, trino):
    def run_sql(sql):
        """Run one Trino statement. Returns a DataFrame for queries, None for DDL/DML."""
        with trino.connect() as conn:
            result = conn.execute(text(sql))
            if result.returns_rows:
                return pd.DataFrame(result.fetchall(), columns=list(result.keys()))
        return None

    def show(df):
        return mo.ui.table(df, selection=None, show_column_summaries=False)

    def ensure_earthquake_events(schema="earthquakes"):
        """Create a stand-in for the dlt table iceberg.<schema>.events, only if it is missing.

        Same columns as the rows dlt/pipeline.py yields (the real dlt table also has _dlt_load_id/_dlt_id).
        Returns True if it created the sample. Never drops or overwrites an existing table.
        """
        run_sql(f"CREATE SCHEMA IF NOT EXISTS iceberg.{schema}")
        exists = not run_sql(
            "SELECT table_name FROM iceberg.information_schema.tables "
            f"WHERE table_schema = '{schema}' AND table_name = 'events'"
        ).empty
        if exists:
            return False
        run_sql(
            f"""
            CREATE TABLE IF NOT EXISTS iceberg.{schema}.events (
                earthquake_id VARCHAR, magnitude DOUBLE, place VARCHAR,
                event_time TIMESTAMP(6) WITH TIME ZONE, updated_time TIMESTAMP(6) WITH TIME ZONE,
                longitude DOUBLE, latitude DOUBLE, depth_km DOUBLE, tsunami BOOLEAN,
                event_type VARCHAR, title VARCHAR, status VARCHAR, magnitude_type VARCHAR,
                significance BIGINT, felt_reports BIGINT, alert_level VARCHAR, url VARCHAR
            ) WITH (format = 'PARQUET')
            """
        )
        if run_sql(f"SELECT count(*) AS n FROM iceberg.{schema}.events")["n"][0] > 0:
            return False
        # A day of quakes shaped like the USGS all_day feed:
        # (id, mag, place, lon, lat, depth_km, magType, hours_ago, tsunami, felt, alert, status)
        quakes = [
            ("ak0256p1kq9", 1.8, "42 km NW of Talkeetna, Alaska", -150.95, 62.66, 48.3, "ml", 0.4, False, None, None, "automatic"),
            ("nc75093312", 0.9, "2 km NW of The Geysers, CA", -122.77, 38.79, 2.1, "md", 0.9, False, None, None, "automatic"),
            ("ci41068952", 2.4, "11 km SE of Ridgecrest, CA", -117.58, 35.56, 7.9, "ml", 1.6, False, 4, None, "reviewed"),
            ("hv74512387", 2.1, "8 km SW of Volcano, Hawaii", -155.29, 19.38, 1.6, "md", 2.2, False, None, None, "automatic"),
            ("pr71473215", 3.1, "45 km N of Hatillo, Puerto Rico", -66.81, 18.89, 34.0, "md", 2.8, False, None, None, "reviewed"),
            ("nn00891234", 1.4, "28 km SE of Mina, Nevada", -117.88, 38.20, 8.5, "ml", 3.5, False, None, None, "automatic"),
            ("us7000q4ab", 4.7, "63 km W of Iquique, Chile", -70.75, -20.21, 35.4, "mb", 4.1, False, None, None, "reviewed"),
            ("us7000q4ac", 5.6, "off the coast of Jalisco, Mexico", -105.80, 19.10, 10.0, "mww", 4.9, False, 12, "green", "reviewed"),
            ("ok2026vxyz", 2.6, "4 km E of Perry, Oklahoma", -97.24, 36.29, 5.0, "ml", 5.6, False, 7, None, "reviewed"),
            ("uw62012345", 1.0, "9 km NE of Mount St. Helens, Washington", -122.12, 46.25, 3.2, "ml", 6.3, False, None, None, "automatic"),
            ("ak0256p2abc", 3.4, "Andreanof Islands, Aleutian Islands, Alaska", -175.60, 51.40, 22.0, "ml", 7.0, False, None, None, "reviewed"),
            ("us7000q4ad", 4.3, "Tonga Islands", -174.20, -18.80, 80.0, "mb", 7.8, False, None, None, "reviewed"),
            ("us7000q4ae", 4.4, "central Mid-Atlantic Ridge", -24.80, 0.90, 10.0, "mb", 8.4, False, None, None, "reviewed"),
            ("us7000q4af", 4.1, "Crete, Greece", 25.40, 35.20, 18.0, "mb", 9.1, False, 6, None, "reviewed"),
            ("us7000q4ag", 4.8, "15 km S of Sindirgi, Turkey", 28.20, 39.10, 9.0, "mww", 9.9, False, 35, None, "reviewed"),
            ("us7000q4ah", 4.0, "3 km SE of Montereale, Italy", 13.25, 42.50, 9.0, "mb", 10.6, False, 20, None, "reviewed"),
            ("us7000q4ai", 3.2, "Reykjanes Peninsula, Iceland", -22.40, 63.90, 5.0, "ml", 11.2, False, 3, None, "reviewed"),
            ("us7000q4aj", 4.5, "southern Iran", 56.90, 27.40, 10.0, "mb", 12.0, False, None, None, "reviewed"),
            ("us7000q4ak", 4.6, "Afar region, Ethiopia", 40.30, 11.20, 10.0, "mb", 12.7, False, None, None, "reviewed"),
            ("us7000q4al", 6.6, "84 km E of Hachinohe, Japan", 142.50, 40.50, 30.0, "mww", 13.5, True, 48, "green", "reviewed"),
            ("us7000q4am", 5.1, "Kepulauan Talaud, Indonesia", 126.70, 4.20, 45.0, "mb", 14.2, False, None, None, "reviewed"),
            ("us7000q4an", 4.9, "12 km SE of Sablayan, Philippines", 121.00, 12.70, 25.0, "mb", 15.0, False, 2, None, "reviewed"),
            ("us7000q4ap", 4.4, "New Britain region, Papua New Guinea", 151.60, -5.60, 55.0, "mb", 15.8, False, None, None, "reviewed"),
            ("us7000q4aq", 5.3, "south of the Fiji Islands", 178.90, -25.20, 560.0, "mb", 16.5, False, None, None, "reviewed"),
            ("us7000q4ar", 6.9, "near the east coast of Kamchatka, Russia", 160.80, 52.90, 19.0, "mww", 17.3, True, 5, "yellow", "reviewed"),
            ("us7000q4as", 4.2, "Hindu Kush region, Afghanistan", 70.90, 36.50, 210.0, "mb", 18.1, False, None, None, "reviewed"),
            ("us7000q4at", 4.3, "Nepal", 85.30, 28.10, 12.0, "mb", 18.9, False, 9, None, "reviewed"),
            ("us7000q4au", 5.0, "Molucca Sea", 126.50, 1.50, 30.0, "mb", 19.6, False, None, None, "reviewed"),
            ("us7000q4av", 4.0, "Kuril Islands", 150.70, 45.80, 40.0, "mb", 20.4, False, None, None, "reviewed"),
            ("us7000q4aw", 5.8, "off the coast of central Chile", -72.60, -33.90, 25.0, "mww", 21.2, False, 64, "green", "reviewed"),
            ("ci41069012", 0.8, "4 km SW of Anza, CA", -116.70, 33.53, 11.8, "ml", 22.0, False, None, None, "automatic"),
            ("ak0256p3def", 1.3, "61 km SE of Cantwell, Alaska", -148.30, 63.05, 70.4, "ml", 23.3, False, None, None, "automatic"),
        ]

        def lit(v):
            if v is None:
                return "NULL"
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, (int, float)):
                return repr(v)
            if isinstance(v, datetime):
                return f"TIMESTAMP '{v.strftime('%Y-%m-%d %H:%M:%S.%f')} UTC'"
            return "'" + str(v).replace("'", "''") + "'"

        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        rows = []
        for (qid, mag, place, lon, lat, depth, mag_type, hours_ago, tsunami, felt, alert, status) in quakes:
            event_time = now - timedelta(hours=hours_ago)
            values = [
                qid, mag, place, event_time, event_time + timedelta(minutes=25), lon, lat, depth, tsunami,
                "earthquake", f"M {mag} - {place}", status, mag_type, int(round(mag * 100 * mag / 6.5)),
                felt, alert, f"https://earthquake.usgs.gov/earthquakes/eventpage/{qid}",
            ]
            rows.append("(" + ", ".join(lit(v) for v in values) + ")")
        run_sql(f"INSERT INTO iceberg.{schema}.events VALUES\n" + ",\n".join(rows))
        return True

    def ensure_shop_tables():
        """Shared lab data (sample-queries.sql, section 2): create if missing, fill only if empty. Never drops."""
        run_sql("CREATE SCHEMA IF NOT EXISTS iceberg.shop WITH (location = 's3://warehouse/polaris_warehouse/shop')")
        run_sql(
            """
            CREATE TABLE IF NOT EXISTS iceberg.shop.orders (
                order_id BIGINT, customer_id BIGINT, order_date DATE, status VARCHAR, total_amount DECIMAL(10, 2)
            ) WITH (format = 'PARQUET')
            """
        )
        run_sql(
            """
            CREATE TABLE IF NOT EXISTS iceberg.shop.order_items (
                item_id BIGINT, order_id BIGINT, product_id BIGINT, quantity INT, unit_price DECIMAL(10, 2)
            ) WITH (format = 'PARQUET')
            """
        )
        if run_sql("SELECT count(*) AS n FROM iceberg.shop.orders")["n"][0] == 0:
            run_sql(
                """
                INSERT INTO iceberg.shop.orders VALUES
                (1001, 1, DATE '2024-01-10', 'shipped', 1349.97), (1002, 2, DATE '2024-01-12', 'shipped', 89.98),
                (1003, 3, DATE '2024-01-15', 'delivered', 449.99), (1004, 1, DATE '2024-01-20', 'delivered', 59.98),
                (1005, 5, DATE '2024-02-01', 'shipped', 1299.99), (1006, 7, DATE '2024-02-05', 'processing', 199.99),
                (1007, 10, DATE '2024-02-10', 'shipped', 639.98), (1008, 4, DATE '2024-02-14', 'delivered', 129.98),
                (1009, 8, DATE '2024-02-20', 'shipped', 399.99), (1010, 6, DATE '2024-03-01', 'processing', 89.99),
                (1011, 12, DATE '2024-03-05', 'shipped', 1749.97), (1012, 15, DATE '2024-03-10', 'delivered', 49.99),
                (1013, 14, DATE '2024-03-15', 'processing', 269.98), (1014, 9, DATE '2024-03-20', 'shipped', 109.99),
                (1015, 20, DATE '2024-03-25', 'delivered', 529.98)
                """
            )
        if run_sql("SELECT count(*) AS n FROM iceberg.shop.order_items")["n"][0] == 0:
            run_sql(
                """
                INSERT INTO iceberg.shop.order_items VALUES
                (1, 1001, 1, 1, 1299.99), (2, 1001, 2, 1, 29.99), (3, 1001, 14, 1, 19.99), (4, 1002, 4, 1, 89.99),
                (5, 1003, 7, 1, 449.99), (6, 1004, 3, 1, 49.99), (7, 1004, 10, 1, 8.99), (8, 1005, 1, 1, 1299.99),
                (9, 1006, 13, 1, 199.99), (10, 1007, 6, 1, 599.99), (11, 1007, 8, 1, 39.99), (12, 1008, 17, 1, 109.99),
                (13, 1008, 14, 1, 19.99), (14, 1009, 5, 1, 399.99), (15, 1010, 4, 1, 89.99), (16, 1011, 1, 1, 1299.99),
                (17, 1011, 7, 1, 449.99), (18, 1012, 3, 1, 49.99), (19, 1013, 13, 1, 199.99), (20, 1013, 12, 1, 69.99),
                (21, 1014, 17, 1, 109.99), (22, 1015, 5, 1, 399.99), (23, 1015, 11, 1, 79.99), (24, 1015, 3, 1, 49.99)
                """
            )

    return ensure_earthquake_events, ensure_shop_tables, run_sql, show


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar(
        [
            mo.md("### Lab 4\n**Data Ingestion**"),
            mo.outline(),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 4 — Data Ingestion

                **Level:** 4 (Advanced) &nbsp;|&nbsp; **Time:** 30 minutes

                **Goal:** ingest data into Iceberg tables from several engines, dlt (Python) and Spark, then query
                it all from Trino. Along the way you'll see how Polaris makes multiple engines work together.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. **Part A:** explore the earthquake data that the dlt pipeline loads from the USGS feed
                    2. **Part B:** write a table from a second engine, then read it and federate it from Trino
                    3. **Part C:** read the dlt-written table from Spark and PyIceberg, then inspect its schema and snapshots
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(POLARIS_HEALTH, S3_ENDPOINT, TRINO_INFO, mo, requests):
    def _reachable(url, **kw):
        try:
            return requests.get(url, timeout=5, **kw).ok
        except requests.RequestException:
            return False

    _checks = {
        "Trino": _reachable(TRINO_INFO, verify=False),
        "Polaris": _reachable(POLARIS_HEALTH),
        "LocalStack": _reachable(f"{S3_ENDPOINT}/_localstack/health"),
    }
    mo.stop(
        not all(_checks.values()),
        mo.callout(
            mo.md(
                "**The lab stack isn't reachable.** "
                + " &nbsp;·&nbsp; ".join(f"{k}: {'up' if v else '**down**'}" for k, v in _checks.items())
                + "\n\nStart it with `podman compose --profile marimo up -d` (or `docker compose --profile marimo up -d`), "
                "then re-run this cell."
            ),
            kind="danger",
        ),
    )
    stack_ok = True
    mo.hstack(
        [
            mo.stat("Healthy", label="Trino", caption="query engine", bordered=True),
            mo.stat("Healthy", label="Polaris", caption="REST catalog", bordered=True),
            mo.stat("Healthy", label="LocalStack", caption="S3 storage", bordered=True),
        ],
        widths="equal",
    )
    return (stack_ok,)


@app.cell(hide_code=True)
def _(ensure_earthquake_events, ensure_shop_tables, mo, run_sql, stack_ok):
    assert stack_ok
    with mo.status.spinner(title="Checking the lab data…"):
        ensure_shop_tables()
        quakes_created = ensure_earthquake_events()
        _cols = set(run_sql("DESCRIBE iceberg.earthquakes.events")["Column"])
        quakes_from_dlt = "_dlt_load_id" in _cols
        quake_rows = int(run_sql("SELECT count(*) AS n FROM iceberg.earthquakes.events")["n"][0])
    data_ready = True
    return data_ready, quake_rows, quakes_created, quakes_from_dlt


@app.cell(hide_code=True)
def _(mo, quake_rows, quakes_created, quakes_from_dlt):
    _run_it = """
    **To load the real data**, run the pipeline service from the repo root (it has no profile, so name it):

    ```bash
    podman compose up dlt-earthquakes        # or: docker compose up dlt-earthquakes
    ```

    It fetches the last 24 hours of quakes from USGS and registers `earthquakes.events` in Polaris
    with its own metadata, replacing the sample. Then re-run this notebook.
    """
    if quakes_from_dlt:
        _out = mo.callout(
            mo.md(f"`iceberg.earthquakes.events` was loaded by the **dlt pipeline** ({quake_rows} rows)."),
            kind="success",
        )
    else:
        _who = "this notebook just created" if quakes_created else "a lab notebook created"
        _out = mo.callout(
            mo.md(
                f"""
                **Sample data: the dlt pipeline hasn't run on this stack.**
                `iceberg.earthquakes.events` is a stand-in that {_who}, with **{quake_rows} sample earthquakes**.
                It has the same columns as `dlt/pipeline.py` (without dlt's `_dlt_load_id` / `_dlt_id` bookkeeping columns),
                so every query below works, but the numbers are illustrative.
                """
                + _run_it
            ),
            kind="warn",
        )
    _out
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Concepts: one catalog, many engines

    Polaris is the **single source of truth** for Iceberg metadata. Several engines can read and write
    the same tables because they all go through the same REST catalog. Data files live once, in S3.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        flowchart LR
            USGS["USGS feed"] --> DLT["dlt (Python)"]
            DLT -->|"writes Parquet"| S3[("LocalStack S3")]
            DLT -->|"register table"| P["Polaris REST Catalog"]
            SP["Spark"] <-->|"read / write"| P
            SP <-->|"Parquet"| S3
            PY["PyIceberg"] <-->|"read / write"| P
            P -.->|"metadata pointers"| S3
            T["Trino"] -->|"loadTable"| P
            T -->|"reads Parquet"| S3
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md("This is the key value of an open catalog: **no vendor lock-in, and any engine can participate**."),
        kind="info",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part A — The dlt earthquake pipeline

    ### Step 1 — Check the pipeline output

    The `dlt-earthquakes` container runs once when the stack starts. Check its logs in a terminal:

    ```bash
    podman logs dlt-earthquakes        # or: docker logs dlt-earthquakes
    ```

    You should see something like:

    ```text
    dlt Earthquake Ingestion Pipeline
    Fetching earthquakes from USGS...
    Got 259 earthquake events
    Pipeline load complete!
    ```
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 2 — Query the earthquake data in Trino

    Total earthquakes loaded:
    """)
    return


@app.cell
def _(data_ready, run_sql):
    assert data_ready
    total_quakes = run_sql("SELECT count(*) AS total_earthquakes FROM iceberg.earthquakes.events")
    return (total_quakes,)


@app.cell(hide_code=True)
def _(mo, quakes_from_dlt, total_quakes):
    mo.hstack(
        [
            mo.stat(
                int(total_quakes["total_earthquakes"][0]),
                label="Total earthquakes",
                caption="from dlt" if quakes_from_dlt else "sample stand-in",
                bordered=True,
            )
        ],
        widths="equal",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    The strongest earthquakes:
    """)
    return


@app.cell
def _(data_ready, run_sql, show):
    assert data_ready
    strongest = run_sql(
        """
        SELECT magnitude, place, event_time, depth_km
        FROM iceberg.earthquakes.events
        ORDER BY magnitude DESC LIMIT 10
        """
    )
    show(strongest)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    Earthquakes by region. A rough split by longitude:
    """)
    return


@app.cell
def _(data_ready, run_sql):
    assert data_ready
    by_region = run_sql(
        """
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
        GROUP BY 1 ORDER BY 2 DESC
        """
    )
    return (by_region,)


@app.cell(hide_code=True)
def _(by_region, mo):
    mo.hstack(
        [
            mo.stat(
                int(r["quakes"]),
                label=r["region"],
                caption=f"avg M{r['avg_mag']} · max M{r['max_mag']}",
                bordered=True,
            )
            for _, r in by_region.iterrows()
        ],
        widths="equal",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 3 — Re-run the pipeline (append mode)

    ```bash
    podman restart dlt-earthquakes && podman logs -f dlt-earthquakes
    # or: docker restart dlt-earthquakes && docker logs -f dlt-earthquakes
    ```

    Wait for it to finish, then run `SELECT count(*) FROM iceberg.earthquakes.events` again.
    The count should roughly double: dlt uses `append` mode, so each run adds the latest batch.

    Every append is a new Iceberg **snapshot**. Here are the snapshots so far, from Trino's `$snapshots` metadata table:
    """)
    return


@app.cell
def _(data_ready, run_sql):
    assert data_ready
    quake_snapshots = run_sql(
        """
        SELECT committed_at, snapshot_id, operation,
               element_at(summary, 'added-records') AS added_records,
               element_at(summary, 'total-records') AS total_records,
               coalesce(element_at(summary, 'engine-name'), 'unknown') AS written_by
        FROM iceberg.earthquakes."events$snapshots"
        ORDER BY committed_at
        """
    )
    return (quake_snapshots,)


@app.cell(hide_code=True)
def _(mo, quake_snapshots):
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(quake_snapshots), label="Snapshots", bordered=True),
                    mo.stat(
                        int((quake_snapshots["operation"] == "append").sum()), label="Appends", bordered=True
                    ),
                ],
                widths="equal",
            ),
            mo.ui.table(quake_snapshots, selection=None, show_column_summaries=False),
            mo.md(
                "_Each pipeline run adds one `append` snapshot, and `total_records` grows. "
                "A table created with `CREATE TABLE` + `INSERT` starts with an empty snapshot followed by the append._"
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 4 — Understand the pipeline code

    The source is `dlt/pipeline.py` (`cat dlt/pipeline.py`). The important parts:
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "Resource (extract + transform)": mo.md(
                """
                ```python
                @dlt.resource(name="events", write_disposition="append", table_format="iceberg")
                def earthquake_events():
                    resp = requests.get(USGS_URL, timeout=30)
                    for f in resp.json().get("features", []):
                        props = f.get("properties", {})
                        coords = f.get("geometry", {}).get("coordinates", [None, None, None])
                        yield {
                            "earthquake_id": f.get("id"),
                            "magnitude": props.get("mag"),
                            "place": props.get("place"),
                            "event_time": ...,   # epoch ms -> ISO timestamp
                            "longitude": coords[0], "latitude": coords[1], "depth_km": coords[2],
                            "tsunami": bool(props.get("tsunami")),
                            ...
                        }
                ```

                - `write_disposition="append"`: each run adds rows; nothing is replaced
                - `table_format="iceberg"`: dlt writes an Iceberg table, not plain Parquet
                - GeoJSON is flattened to rows during `yield`
                """
            ),
            "Pipeline (load)": mo.md(
                """
                ```python
                pipeline = dlt.pipeline(
                    pipeline_name="earthquake_ingest",
                    destination="filesystem",      # Parquet files to s3://warehouse
                    dataset_name="earthquakes",
                )
                info = pipeline.run(earthquake_events())
                ```

                `destination="filesystem"` writes Parquet files to S3, using the bucket and credentials in `dlt/.dlt/*.toml`.
                """
            ),
            "register_in_polaris()": mo.md(
                """
                ```python
                cat = load_catalog("polaris", **POLARIS_CONFIG)
                latest = newest "*.metadata.json" under earthquakes/events/metadata
                if "events" in cat.list_tables("earthquakes"):
                    if cat.load_table("earthquakes.events").metadata_location == latest:
                        return                    # already up to date
                    cat.drop_table("earthquakes.events")
                cat.register_table("earthquakes.events", latest)
                ```

                This registers the Iceberg table metadata in Polaris so Trino and Spark can find it.
                Registering doesn't copy any data; it only points the catalog at an existing `metadata.json`.
                """
            ),
            "Table columns": mo.md(
                """
                | Column | Type | From USGS |
                |--------|------|-----------|
                | `earthquake_id` | varchar | `id` |
                | `magnitude` | double | `mag` |
                | `place`, `title` | varchar | `place`, `title` |
                | `event_time`, `updated_time` | timestamp (UTC) | `time`, `updated` (epoch ms) |
                | `longitude`, `latitude`, `depth_km` | double | `geometry.coordinates` |
                | `tsunami` | boolean | `tsunami` (0/1) |
                | `event_type`, `status`, `magnitude_type`, `alert_level`, `url` | varchar | `type`, `status`, `magType`, `alert`, `url` |
                | `significance`, `felt_reports` | bigint | `sig`, `felt` |
                | `_dlt_load_id`, `_dlt_id` | varchar | added by dlt |
                """
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part B — Writing from a second engine

    ### Step 5 — Open Jupyter (Spark)

    Spark runs in the optional `spark` profile:

    ```bash
    podman compose --profile spark up -d        # or: docker compose --profile spark up -d
    ```

    Then go to http://localhost:8888?token=spark123 and create a new Python 3 notebook,
    or open one in the `work/` folder. Spark's catalog is called `polaris`.

    ### Step 6 — Write a new table from Spark

    These are the Spark cells to run in Jupyter:
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "1. Check existing data": mo.md(
                """
                ```python
                spark.sql("SELECT count(*) FROM polaris.shop.orders").show()
                ```
                """
            ),
            "2. Create the table": mo.md(
                '''
                ```python
                spark.sql("""
                  CREATE TABLE IF NOT EXISTS polaris.shop.daily_summary (
                    order_date DATE,
                    num_orders INT,
                    total_revenue DOUBLE
                  )
                """)
                ```
                '''
            ),
            "3. Insert aggregated data": mo.md(
                '''
                ```python
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
                '''
            ),
            "4. Verify": mo.md(
                """
                ```python
                spark.sql("SELECT * FROM polaris.shop.daily_summary ORDER BY order_date").show()
                ```
                """
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    #### No Spark? PyIceberg plays the second engine

    So that this notebook runs on its own, the next cell creates the same `shop.daily_summary` table with
    **PyIceberg**, a separate engine that talks to Polaris directly and never touches Trino.
    It reads `shop.orders`, aggregates per day in pandas and appends the result.
    If `daily_summary` already has rows (for example from Spark), the cell leaves them alone.

    The config has **no S3 keys**: Polaris vends temporary credentials (see Lab 16).
    """)
    return


@app.cell
def _(CATALOG_NAME, POLARIS, S3_ENDPOINT, data_ready, load_catalog, pa):
    assert data_ready
    catalog = load_catalog(
        "polaris",
        **{
            "type": "rest",
            "uri": f"{POLARIS}/api/catalog",
            "warehouse": CATALOG_NAME,
            "credential": "root:s3cr3t",
            "scope": "PRINCIPAL_ROLE:ALL",
            "header.Polaris-Realm": "POLARIS",
            "header.X-Iceberg-Access-Delegation": "vended-credentials",
            "s3.endpoint": S3_ENDPOINT,
            "s3.path-style-access": "true",
            "s3.region": "us-east-1",
        },
    )

    daily_schema = pa.schema(
        [("order_date", pa.date32()), ("num_orders", pa.int32()), ("total_revenue", pa.float64())]
    )
    daily_summary = catalog.create_table_if_not_exists("shop.daily_summary", schema=daily_schema)

    daily_written = False
    if daily_summary.scan(limit=1).to_arrow().num_rows == 0:
        _orders = catalog.load_table("shop.orders").scan(selected_fields=("order_date", "total_amount")).to_pandas()
        _daily = (
            _orders.assign(total_amount=_orders["total_amount"].astype(float))
            .groupby("order_date", as_index=False)
            .agg(num_orders=("total_amount", "size"), total_revenue=("total_amount", "sum"))
        )
        daily_summary.append(pa.Table.from_pandas(_daily, schema=daily_schema, preserve_index=False))
        daily_written = True
    return catalog, daily_summary, daily_written


@app.cell(hide_code=True)
def _(daily_summary, daily_written, mo):
    _snap = daily_summary.current_snapshot()
    _engine = (_snap.summary.additional_properties.get("engine-name") if _snap else None) or "pyiceberg / spark"
    mo.callout(
        mo.md(
            f"Wrote **`shop.daily_summary`** with PyIceberg (snapshot `{_snap.snapshot_id}`)."
            if daily_written
            else f"`shop.daily_summary` already had data, so it was left untouched (last written by **{_engine}**)."
        ),
        kind="success" if daily_written else "neutral",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 7 — Read the other engine's data from Trino

    Trino can **immediately** see what Spark or PyIceberg wrote. First list the tables in `shop`:
    """)
    return


@app.cell
def _(daily_summary, run_sql, show):
    assert daily_summary is not None
    show(run_sql("SHOW TABLES IN iceberg.shop"))
    return


@app.cell
def _(daily_summary, run_sql, show):
    assert daily_summary is not None
    show(run_sql("SELECT * FROM iceberg.shop.daily_summary ORDER BY order_date"))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            "This works because every engine uses **Polaris** as the catalog. The writer commits a new "
            "metadata pointer, and Trino's next `loadTable` call picks it up. There's no export and no refresh step."
        ),
        kind="success",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 8 — Cross-engine federation

    Combine the second engine's table (Iceberg) with Postgres data in one Trino query:
    """)
    return


@app.cell
def _(daily_summary, run_sql, show):
    assert daily_summary is not None
    show(
        run_sql(
            """
            SELECT
              ds.order_date,
              ds.num_orders,
              round(ds.total_revenue, 2) AS revenue,
              (SELECT count(DISTINCT country)
               FROM postgres.public.customers) AS total_countries
            FROM iceberg.shop.daily_summary ds
            ORDER BY ds.order_date
            """
        )
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    One more: orders and customers joined with a count from the dlt table, three writers in one query.
    """)
    return


@app.cell
def _(data_ready, run_sql, show):
    assert data_ready
    show(
        run_sql(
            """
            SELECT
              c.name AS customer, c.country,
              o.order_id, o.total_amount,
              e_count.quake_count
            FROM iceberg.shop.orders o
            JOIN postgres.public.customers c ON o.customer_id = c.customer_id
            CROSS JOIN (
              SELECT count(*) AS quake_count FROM iceberg.earthquakes.events
            ) e_count
            ORDER BY o.total_amount DESC
            LIMIT 10
            """
        )
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    | Data | Lives in | Written by |
    |------|----------|------------|
    | `postgres.public.customers` | PostgreSQL | SQL init script |
    | `iceberg.shop.orders` | Iceberg on S3 | Trino (`sample-queries.sql`) or Spark |
    | `iceberg.shop.daily_summary` | Iceberg on S3 | Spark, or PyIceberg above |
    | `iceberg.earthquakes.events` | Iceberg on S3 | dlt |

    Different engines wrote the data, and Trino reads all of it in one query.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md("""
            ---
            ## Part C — Reading dlt data from other engines

            ### Step 9 — Read the dlt-written data from Spark

            In Jupyter:
            """),
            mo.md(
                '''
                ```python
                spark.sql("""
                  SELECT magnitude, place, event_time
                  FROM polaris.earthquakes.events
                  WHERE magnitude > 4
                  ORDER BY magnitude DESC
                """).show(20, truncate=False)
                ```
                '''
            ),
            mo.md("""
            Without Spark, here's the same read through PyIceberg. The filter is pushed into the scan, so files whose
            min/max statistics rule out `magnitude > 4` are skipped:
            """),
        ]
    )
    return


@app.cell
def _(catalog):
    events = catalog.load_table("earthquakes.events")
    big_quakes = (
        events.scan(row_filter="magnitude > 4", selected_fields=("magnitude", "place", "event_time"))
        .to_pandas()
        .sort_values("magnitude", ascending=False)
        .head(20)
    )
    return big_quakes, events


@app.cell(hide_code=True)
def _(big_quakes, mo):
    mo.vstack(
        [
            mo.ui.table(big_quakes, selection=None, show_column_summaries=False),
            mo.callout(
                mo.md(
                    "dlt wrote the data, Polaris catalogued it, and Spark or PyIceberg reads it: "
                    "**three different tools, zero data movement.**"
                ),
                kind="success",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Explore the table with PyIceberg

    PyIceberg reads the same metadata Trino and Spark see: the table identity, schema and snapshot history.
    """)
    return


@app.cell
def _(events):
    events_name = ".".join(events.name())
    events_schema = [
        {"id": f.field_id, "name": f.name, "type": str(f.field_type), "required": f.required}
        for f in events.schema().fields
    ]
    events_history = [
        {"snapshot_id": h.snapshot_id, "timestamp_ms": h.timestamp_ms} for h in events.history()
    ]
    return events_history, events_name, events_schema


@app.cell(hide_code=True)
def _(datetime, events, events_history, events_name, events_schema, mo, pd, timezone):
    _hist = pd.DataFrame(events_history)
    if not _hist.empty:
        _hist["committed (UTC)"] = _hist.pop("timestamp_ms").map(
            lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        )
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(events_name, label="Table", bordered=True),
                    mo.stat(len(events_schema), label="Columns", bordered=True),
                    mo.stat(len(events_history), label="Snapshots", bordered=True),
                    mo.stat(f"v{events.format_version}", label="Iceberg format", bordered=True),
                ],
                widths="equal",
            ),
            mo.md(f"**Location:** `{events.location()}`"),
            mo.ui.tabs(
                {
                    "Schema": mo.ui.table(pd.DataFrame(events_schema), selection=None, show_column_summaries=False),
                    "Snapshot history": mo.ui.table(_hist, selection=None, show_column_summaries=False),
                }
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Wrap-up
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.accordion(
        {
            "Key takeaways": mo.md(
                """
                1. Polaris is the single source of truth for Iceberg metadata, and every engine goes through its REST API
                2. dlt turns an API feed into an Iceberg table (`table_format="iceberg"`, `write_disposition="append"`)
                3. `register_table` points the catalog at existing metadata without copying data
                4. A table written by Spark or PyIceberg is visible to Trino immediately, with no refresh step
                5. Every append is a snapshot; `$snapshots` / `table.history()` show who wrote what, and when
                """
            ),
            "Exercises": mo.md(
                """
                1. Find all earthquakes with `magnitude > 4`. How many are there?
                2. **Modify the earthquake query** to find all earthquakes with `tsunami = true`. How many are there?
                3. **Create a Spark table** called `polaris.earthquakes.magnitude_bins` with columns `bin` (string) and
                   `count` (int). Populate it with magnitude ranges: `<2`, `2-3`, `3-4`, `4-5`, `5+`.
                4. **Query `magnitude_bins` from Trino** to verify cross-engine visibility.
                   Do the same for `daily_summary`, if Spark created it.
                5. **Use `DESCRIBE`** in Trino to compare the schema of a dlt-created table with a Spark-created table. Any differences?
                6. Use PyIceberg to inspect the schema of `shop.orders` (`catalog.load_table("shop.orders").schema()`),
                   and compare it with `DESCRIBE iceberg.shop.orders` in Trino.
                7. **Challenge:** use PyIceberg to read the snapshot history of `earthquakes.events`.
                   How many snapshots exist after re-running dlt?
                8. **Challenge:** write a Python script (outside of dlt) that uses `requests` to fetch weather data
                   from a public API and inserts it into a new Iceberg table via Spark SQL (or PyIceberg).
                """
            ),
            "Next lab": mo.md("**Lab 5 — API Mastery**: drive the Polaris management and catalog REST APIs directly."),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
