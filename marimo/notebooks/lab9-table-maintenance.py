import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 9 — Table Maintenance")


@app.cell(hide_code=True)
def _():
    import json
    import os
    import re
    import statistics
    import time

    import marimo as mo
    import pandas as pd
    import requests
    import urllib3
    from pyiceberg.catalog import load_catalog
    from sqlalchemy import create_engine, text

    urllib3.disable_warnings()

    TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
    POLARIS = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8181"
    POLARIS_HEALTH = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8182/q/health"
    S3_ENDPOINT = f"http://{os.environ.get('S3_HOST', 'localhost')}:4566"
    TABLE = "iceberg.shop.sensor_readings"

    trino = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (
        POLARIS,
        POLARIS_HEALTH,
        S3_ENDPOINT,
        TABLE,
        json,
        load_catalog,
        mo,
        pd,
        re,
        requests,
        statistics,
        text,
        time,
        trino,
    )


@app.cell(hide_code=True)
def _(mo, pd, re, statistics, text, time, trino):
    def sql(query):
        """Run a Trino query and return a DataFrame."""
        with trino.connect() as _conn:
            return pd.read_sql(text(query), _conn)

    def execute(*statements):
        """Run statements on one Trino connection (so SET SESSION applies); return the last result rows."""
        _rows = []
        with trino.connect() as _conn:
            for _s in statements:
                _res = _conn.execute(text(_s))
                _rows = [tuple(r) for r in _res.fetchall()] if _res.returns_rows else []
        return _rows

    def table_stats(table):
        """File / snapshot / manifest / row counts from Iceberg metadata tables."""
        _cat, _ns, _tbl = table.split(".")
        _f = sql(f'SELECT count(*) AS n, coalesce(sum(record_count), 0) AS r, coalesce(sum(file_size_in_bytes), 0) AS b FROM {_cat}.{_ns}."{_tbl}$files"')
        return {
            "files": int(_f["n"].iloc[0]),
            "rows": int(_f["r"].iloc[0]),
            "bytes": int(_f["b"].iloc[0]),
            "snapshots": int(sql(f'SELECT count(*) AS n FROM {_cat}.{_ns}."{_tbl}$snapshots"')["n"].iloc[0]),
            "manifests": int(sql(f'SELECT count(*) AS n FROM {_cat}.{_ns}."{_tbl}$manifests"')["n"].iloc[0]),
        }

    def benchmark(query, runs=3):
        """Median wall-clock time over a few runs (a single run of a tiny query is mostly noise)."""
        _times = []
        _df = None
        for _ in range(runs):
            _start = time.time()
            _df = sql(query)
            _times.append(time.time() - _start)
        return statistics.median(_times), _df

    def explain_analyze(query):
        """Run EXPLAIN ANALYZE and pull out the table-scan split count and input rows."""
        _plan = sql(f"EXPLAIN ANALYZE {query}").iloc[0, 0]
        _splits = re.findall(r"Splits: (\d+)", _plan)
        _input = re.search(r"TableScan\[.*?Input: (\d+) rows", _plan, re.S)
        return {
            "splits": int(_splits[-1]) if _splits else None,
            "input_rows": int(_input.group(1)) if _input else None,
            "plan": _plan,
        }

    def stat_row(stats, caption=""):
        return mo.hstack(
            [
                mo.stat(stats["files"], label="Data files", caption=caption, bordered=True),
                mo.stat(stats["snapshots"], label="Snapshots", bordered=True),
                mo.stat(stats["manifests"], label="Manifests", bordered=True),
                mo.stat(stats["rows"], label="Rows", caption=f"{stats['bytes']:,} bytes on S3", bordered=True),
            ],
            widths="equal",
        )

    def show(df, page_size=10):
        return mo.ui.table(df, selection=None, show_column_summaries=False, page_size=page_size)

    return benchmark, execute, explain_analyze, show, sql, stat_row, table_stats


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar([mo.md("### Lab 9\n**Table Maintenance**"), mo.outline()])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 9 — Iceberg Table Maintenance

                **Level:** 5 (Advanced) &nbsp;|&nbsp; **Time:** 40 minutes

                **Goal:** See firsthand why table maintenance matters. Create a real performance problem with
                small files, measure the impact, fix it with compaction, and learn the full maintenance toolkit.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Create `iceberg.shop.sensor_readings` and write it with 20 one-row micro-batches
                    2. Measure the damage: files, snapshots, manifests, splits and query time
                    3. **Compact** the table and measure again
                    4. Expire old snapshots, remove orphan files and evolve the partition spec
                    5. Confirm from PyIceberg that every engine sees the result, and build a table health report

                    The maintenance steps change the table, so each one waits for you to click its **▶ Run** button.
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(POLARIS_HEALTH, mo, requests, sql):
    try:
        _trino_version = sql("SELECT version() AS v")["v"].iloc[0]
    except Exception:
        _trino_version = None
    try:
        _polaris_ok = requests.get(POLARIS_HEALTH, timeout=5).ok
    except requests.RequestException:
        _polaris_ok = False

    mo.stop(
        _trino_version is None or not _polaris_ok,
        mo.callout(
            mo.md(
                f"""
                **The lab stack isn't reachable.**
                Trino: {"up" if _trino_version else "**down**"} &nbsp;·&nbsp; Polaris: {"up" if _polaris_ok else "**down**"}

                Start it with `podman compose --profile marimo up -d` (or `docker compose …`), then re-run this cell.
                """
            ),
            kind="danger",
        ),
    )
    stack_ok = True
    mo.hstack(
        [
            mo.stat("Healthy", label="Trino", caption=f"version {_trino_version}", bordered=True),
            mo.stat("Healthy", label="Polaris", caption="REST catalog", bordered=True),
        ],
        widths="equal",
    )
    return (stack_ok,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Concepts

    Iceberg tables accumulate overhead over time:

    | Problem | Symptom | Solution | Trino command |
    |---------|---------|----------|---------------|
    | Many small files | Slow reads, high S3 cost | Compaction (rewrite files) | `ALTER TABLE ... EXECUTE optimize` |
    | Old snapshots piling up | Metadata bloat | Expire snapshots | `ALTER TABLE ... EXECUTE expire_snapshots` |
    | Leftover data files | Wasted storage | Remove orphan files | `ALTER TABLE ... EXECUTE remove_orphan_files` |
    | Changing query patterns | Scans too much data | Partition evolution | `ALTER TABLE ... SET PROPERTIES` |
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.mermaid(
                """
                flowchart LR
                    T["Trino<br/>runs maintenance"] -->|commit new metadata| P["Polaris<br/>REST catalog"]
                    S["Spark"] -->|commit| P
                    P -->|metadata pointer| M[("S3: metadata + data files")]
                    P -->|loadTable| Py["PyIceberg<br/>sees the result instantly"]
                """
            ),
            mo.md(
                "**Key point:** Polaris coordinates the metadata. You can run maintenance from any engine (Trino, Spark), "
                "and every other engine sees the updated metadata immediately through the shared catalog."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part A — Why maintenance matters (performance demo)

    **The scenario:** an IoT pipeline sends sensor readings every few seconds. Each micro-batch creates a tiny
    Parquet file. After many inserts the table has dozens of small files, each needing a separate S3 GET to read,
    and queries slow down.

    ## Step 1 — Create the sensor table

    This lab owns `iceberg.shop.sensor_readings`, so the cell drops and recreates it on every run.

    > **Why not `DROP TABLE` in Trino?** Trino asks Polaris to *purge* the files when it drops a table, and this
    > Polaris has `DROP_WITH_PURGE_ENABLED` switched off, so the drop fails with HTTP 403. We drop the catalog entry
    > through PyIceberg instead (no purge), and Trino then creates a new table at a new location.
    """)
    return


@app.cell
def _(POLARIS, S3_ENDPOINT, load_catalog):
    # PyIceberg talks to the same Polaris catalog Trino uses. No S3 keys: Polaris vends them.
    catalog = load_catalog(
        "polaris",
        **{
            "type": "rest",
            "uri": f"{POLARIS}/api/catalog",
            "warehouse": "polaris_warehouse",
            "credential": "root:s3cr3t",
            "scope": "PRINCIPAL_ROLE:ALL",
            "header.Polaris-Realm": "POLARIS",
            "header.X-Iceberg-Access-Delegation": "vended-credentials",
            "s3.endpoint": S3_ENDPOINT,
            "s3.path-style-access": "true",
            "s3.region": "us-east-1",
        },
    )
    return (catalog,)


@app.cell
def _(catalog, execute, stack_ok):
    assert stack_ok
    if catalog.table_exists("shop.sensor_readings"):
        catalog.drop_table("shop.sensor_readings")

    execute(
        "CREATE SCHEMA IF NOT EXISTS iceberg.shop WITH (location = 's3://warehouse/polaris_warehouse/shop')",
        """
        CREATE TABLE iceberg.shop.sensor_readings (
          sensor_id VARCHAR,
          temperature DOUBLE,
          humidity DOUBLE,
          reading_time TIMESTAMP(6) WITH TIME ZONE
        )
        """,
    )
    table_uuid = str(catalog.load_table("shop.sensor_readings").metadata.table_uuid)
    return (table_uuid,)


@app.cell(hide_code=True)
def _(mo, table_uuid):
    mo.callout(mo.md(f"Table `iceberg.shop.sensor_readings` created (table UUID `{table_uuid[:8]}…`)."), kind="success")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 2 — Simulate micro-batch writes (20 small inserts)

    Each `INSERT` creates a **new data file** and a **new snapshot**, just like a streaming pipeline:
    """)
    return


@app.cell
def _(TABLE, execute, mo, table_uuid):
    sensor_data = [
        ("sensor-01", 22.5, 45.0),
        ("sensor-02", 23.1, 42.3),
        ("sensor-03", 21.8, 48.7),
        ("sensor-01", 22.7, 44.5),
        ("sensor-02", 23.4, 41.9),
        ("sensor-03", 21.5, 49.2),
        ("sensor-01", 22.9, 43.8),
        ("sensor-02", 23.8, 40.5),
        ("sensor-03", 21.2, 50.1),
        ("sensor-01", 23.0, 44.0),
        ("sensor-02", 24.1, 39.8),
        ("sensor-03", 20.9, 51.3),
        ("sensor-01", 23.2, 43.2),
        ("sensor-02", 24.5, 38.7),
        ("sensor-03", 20.6, 52.0),
        ("sensor-01", 23.5, 42.5),
        ("sensor-02", 24.8, 37.9),
        ("sensor-03", 20.3, 53.1),
        ("sensor-01", 23.8, 41.8),
        ("sensor-02", 25.0, 37.0),
    ]
    with mo.status.progress_bar(total=len(sensor_data), title="Micro-batch inserts") as _bar:
        for _sid, _temp, _hum in sensor_data:
            execute(f"INSERT INTO {TABLE} VALUES ('{_sid}', {_temp}, {_hum}, CURRENT_TIMESTAMP)")
            _bar.update(subtitle=f"{_sid} temp={_temp}")
    inserted_for = table_uuid
    return inserted_for, sensor_data


@app.cell(hide_code=True)
def _(mo, sensor_data):
    mo.callout(mo.md(f"**{len(sensor_data)} individual inserts = {len(sensor_data)} tiny files.**"), kind="warn")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 3 — Observe the damage

    ```sql
    SELECT count(*) AS file_count     FROM iceberg.shop."sensor_readings$files";
    SELECT count(*) AS snapshot_count FROM iceberg.shop."sensor_readings$snapshots";
    SELECT count(*) AS manifest_count FROM iceberg.shop."sensor_readings$manifests";
    ```

    Expected: **20 data files, 20 snapshots, 20+ manifests**, for just 20 rows of data.
    """)
    return


@app.cell
def _(TABLE, inserted_for, sql, table_stats):
    stats_before = table_stats(TABLE)
    files_before_df = sql(
        """
        SELECT file_path, file_format, record_count, file_size_in_bytes
        FROM iceberg.shop."sensor_readings$files"
        """
    )
    files_before = stats_before["files"]
    snaps_before = stats_before["snapshots"]
    _ = inserted_for
    return files_before, files_before_df, snaps_before, stats_before


@app.cell(hide_code=True)
def _(files_before, files_before_df, mo, show, stat_row, stats_before):
    _avg = int(files_before_df["file_size_in_bytes"].mean()) if len(files_before_df) else 0
    mo.vstack(
        [
            mo.md("**Table state before compaction**"),
            stat_row(stats_before, caption=f"≈ {_avg:,} bytes each"),
            mo.callout(mo.md(f"That's **{files_before} separate S3 requests** for every query."), kind="danger"),
            mo.md("**Individual file details** (each holds just 1 row):"),
            show(files_before_df),
            mo.callout(
                mo.md(
                    "**Question:** Each file holds just 1 row. What's the overhead? How much of each file is metadata "
                    "(Parquet header, footer, column-chunk statistics) versus actual data?"
                ),
                kind="neutral",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 4 — Benchmark the query BEFORE compaction

    We run the report query three times and take the median, then check the plan with `EXPLAIN ANALYZE`.
    (You can also watch the query in the Trino Web UI at [https://localhost:8443/ui/](https://localhost:8443/ui/).)
    """)
    return


@app.cell
def _():
    REPORT_QUERY = """
        SELECT
          sensor_id,
          count(*) AS readings,
          round(avg(temperature), 2) AS avg_temp,
          round(avg(humidity), 2) AS avg_humidity,
          min(reading_time) AS first_reading,
          max(reading_time) AS last_reading
        FROM iceberg.shop.sensor_readings
        GROUP BY sensor_id
        ORDER BY sensor_id
    """
    PLAN_QUERY = """
        SELECT sensor_id, avg(temperature) AS avg_temp
        FROM iceberg.shop.sensor_readings
        GROUP BY sensor_id
    """
    return PLAN_QUERY, REPORT_QUERY


@app.cell
def _(PLAN_QUERY, REPORT_QUERY, benchmark, explain_analyze, files_before):
    time_before, report_before = benchmark(REPORT_QUERY)
    plan_before = explain_analyze(PLAN_QUERY)
    _ = files_before
    return plan_before, report_before, time_before


@app.cell(hide_code=True)
def _(mo, plan_before, report_before, show, time_before):
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(f"{time_before:.3f}s", label="Query time BEFORE", caption="median of 3 runs", bordered=True),
                    mo.stat(plan_before["splits"], label="Splits", caption="one per data file", bordered=True),
                    mo.stat(plan_before["input_rows"], label="Rows scanned", bordered=True),
                ],
                widths="equal",
            ),
            show(report_before),
            mo.accordion({"EXPLAIN ANALYZE plan": mo.plain_text(plan_before["plan"])}),
            mo.md("Look for `Input: 20 rows` across many splits: Trino opens 20 separate files."),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 5 — Run compaction

    Rewrite the 20 tiny files into 1-2 larger files:

    ```sql
    ALTER TABLE iceberg.shop.sensor_readings EXECUTE optimize;
    ```
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    # Every maintenance step records what it did here, keyed by table UUID, so the
    # "after" cells always render (and say so when a step hasn't been run yet).
    get_maint, set_maint = mo.state({})
    optimize_btn = mo.ui.run_button(label="▶ Run compaction (optimize)", kind="warn")
    optimize_btn
    return get_maint, optimize_btn, set_maint


@app.cell
def _(TABLE, execute, files_before, mo, optimize_btn, set_maint, table_uuid):
    mo.stop(not optimize_btn.value, mo.md("_Click **▶ Run compaction** to rewrite the small files._"))

    with mo.status.spinner(title="Compacting…"):
        _result = execute(f"ALTER TABLE {TABLE} EXECUTE optimize")
    set_maint(lambda log: {**log, "optimize": {"uuid": table_uuid, "result": dict(_result), "files_before": files_before}})
    mo.callout(mo.md(f"**Compaction complete!** `{dict(_result)}`"), kind="success")
    return


@app.cell(hide_code=True)
def _(get_maint, table_uuid):
    # Snapshot the log once; marimo re-runs this cell whenever set_maint() fires,
    # so ran() and maint_log always agree.
    maint_log = get_maint()

    def ran(step):
        """True if a maintenance step has been run against the current table."""
        return maint_log.get(step, {}).get("uuid") == table_uuid
    return maint_log, ran


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 6 — Observe the fix

    Same metadata queries as Step 3. Expected: **1-2 data files** holding all 20 rows, and one more snapshot
    (compaction is a commit too).
    """)
    return


@app.cell
def _(TABLE, files_before, maint_log, sql, table_stats):
    stats_after = table_stats(TABLE)
    files_after_df = sql(
        """
        SELECT file_path, file_format, record_count, file_size_in_bytes
        FROM iceberg.shop."sensor_readings$files"
        """
    )
    files_after = stats_after["files"]
    snaps_after = stats_after["snapshots"]
    _ = (maint_log, files_before)
    return files_after, files_after_df, snaps_after, stats_after


@app.cell(hide_code=True)
def _(files_after_df, mo, ran, show, stat_row, stats_after):
    mo.vstack(
        [
            mo.md("**Table state after compaction**" if ran("optimize") else "**Current table state**"),
            stat_row(stats_after),
            mo.callout("After compaction, all rows sit in one file:", kind="success")
            if ran("optimize")
            else mo.callout(
                mo.md("Compaction hasn't run yet, so this is still the small-files table. Click **▶ Run compaction** in Step 5."),
                kind="warn",
            ),
            show(files_after_df),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 7 — Benchmark the query AFTER compaction

    Run the exact same query and plan again.
    """)
    return


@app.cell
def _(PLAN_QUERY, REPORT_QUERY, benchmark, explain_analyze, files_after):
    time_after, report_after = benchmark(REPORT_QUERY)
    plan_after = explain_analyze(PLAN_QUERY)
    _ = files_after
    return plan_after, time_after


@app.cell(hide_code=True)
def _(mo, plan_after, plan_before, ran, time_after):
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(f"{time_after:.3f}s", label="Query time AFTER" if ran("optimize") else "Query time (not compacted yet)", caption="median of 3 runs", bordered=True),
                    mo.stat(plan_after["splits"], label="Splits", caption=f"was {plan_before['splits']}", bordered=True),
                    mo.stat(plan_after["input_rows"], label="Rows scanned", bordered=True),
                ],
                widths="equal",
            ),
            mo.accordion({"EXPLAIN ANALYZE plan": mo.plain_text(plan_after["plan"])}),
            mo.md("Look for the difference: fewer splits, fewer files opened."),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 8 — The impact summary
    """)
    return


@app.cell(hide_code=True)
def _(
    files_after,
    files_before,
    mo,
    plan_after,
    plan_before,
    ran,
    snaps_after,
    snaps_before,
    stats_after,
    stats_before,
    time_after,
    time_before,
):
    speedup = time_before / time_after if time_after > 0 else 0
    _rows_per_file_before = stats_before["rows"] / max(files_before, 1)
    _rows_per_file_after = stats_after["rows"] / max(files_after, 1)
    _table = mo.md(
        f"""
        | Metric | BEFORE | AFTER | Change |
        |--------|--------|-------|--------|
        | **Data files** | {files_before} | {files_after} | {files_before} → {files_after} |
        | **Snapshots** | {snaps_before} | {snaps_after} | +{snaps_after - snaps_before} (compaction) |
        | **S3 GETs (splits) per query** | {plan_before['splits']} | {plan_after['splits']} | **{plan_before['splits']}x → {plan_after['splits']}x** |
        | **Rows per file** | {_rows_per_file_before:.0f} | {_rows_per_file_after:.0f} | |
        | **Query time** | {time_before:.3f}s | {time_after:.3f}s | **{speedup:.1f}x** |
        """
    )
    mo.vstack(
        [
            _table
            if ran("optimize")
            else mo.callout(mo.md("The **AFTER** column will show results once you run compaction in Step 5. Here's the table so far:"), kind="warn"),
            _table if not ran("optimize") else mo.md(""),
            mo.callout(
                mo.md(
                    "With only 20 rows, query time is dominated by planning and network round-trips, so the speedup is small "
                    "and noisy. The file and split counts are the real signal.\n\n"
                    "**At scale:** imagine 10,000 micro-batches per day. After a month that's 300,000 tiny files. "
                    "Every query must open all of them. Without compaction, queries that should take seconds take minutes."
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part B — The full maintenance toolkit

    Now that you've seen why maintenance matters, here's the complete toolkit.

    ## Step 9 — Expire old snapshots

    After compaction the table has 21 snapshots (20 inserts + 1 compaction). The old pre-compaction snapshots are
    useless now: they point to files that were rewritten. Expiring them also **deletes the data files that only those
    snapshots referenced**, which here means the 20 tiny files.

    ```sql
    ALTER TABLE iceberg.shop.sensor_readings EXECUTE expire_snapshots(retention_threshold => '1m');
    ```

    Trino refuses thresholds below `iceberg.expire-snapshots.min-retention` (**7 days** by default), so `'1m'` on its
    own fails with *"Retention specified (1.00m) is shorter than the minimum retention configured in the system (7.00d)"*.
    For the demo we lower the minimum for **this session only** with
    `SET SESSION iceberg.expire_snapshots_min_retention = '0s'`. Keep the 7-day guard in production: it protects
    time travel and readers that are still running.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    expire_retention = mo.ui.dropdown(
        ["0s", "1m", "1h", "7d"], value="0s", label="retention_threshold"
    )
    expire_btn = mo.ui.run_button(label="▶ Expire snapshots", kind="warn")
    mo.hstack(
        [expire_retention, expire_btn, mo.md("_`1m` keeps everything if the inserts ran less than a minute ago_")],
        justify="start",
        gap=1,
    )
    return expire_btn, expire_retention


@app.cell
def _(TABLE, execute, expire_btn, expire_retention, mo, set_maint, table_stats, table_uuid):
    mo.stop(not expire_btn.value, mo.md("_Click **▶ Expire snapshots** to run this step._"))

    _before = table_stats(TABLE)
    execute(
        "SET SESSION iceberg.expire_snapshots_min_retention = '0s'",
        f"ALTER TABLE {TABLE} EXECUTE expire_snapshots(retention_threshold => '{expire_retention.value}')",
    )
    _after = table_stats(TABLE)
    set_maint(lambda log: {**log, "expire": {"uuid": table_uuid, "before": _before, "after": _after, "retention": expire_retention.value}})
    return


@app.cell(hide_code=True)
def _(maint_log, mo, ran):
    if ran("expire"):
        _e = maint_log["expire"]
        _out = mo.vstack(
            [
                mo.hstack(
                    [
                        mo.stat(_e["before"]["snapshots"], label="Snapshots before expiration", bordered=True),
                        mo.stat(_e["after"]["snapshots"], label="Snapshots after expiration", caption=f"retention {_e['retention']}", bordered=True),
                        mo.stat(_e["before"]["snapshots"] - _e["after"]["snapshots"], label="Removed", bordered=True),
                    ],
                    widths="equal",
                ),
                mo.callout(
                    mo.md("**Question:** How many snapshots remain? Why does Iceberg always keep at least one?"),
                    kind="neutral",
                ),
            ]
        )
    else:
        _out = mo.callout(
            mo.md("Snapshot expiry hasn't run yet. Pick a retention and click **▶ Expire snapshots** (run compaction first to see the full effect)."),
            kind="neutral",
        )
    _out
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 10 — Remove orphan files

    *Orphans* are files in the table's location that **no metadata references at all**: leftovers from failed or
    aborted writes, or files written by a job that crashed before it committed. `expire_snapshots` can't see them
    because they were never part of a snapshot. This cleans up wasted S3 storage:

    ```sql
    ALTER TABLE iceberg.shop.sensor_readings EXECUTE remove_orphan_files(retention_threshold => '1m');
    ```

    Like expiry, Trino enforces a minimum retention (`iceberg.remove_orphan_files_min_retention`, 7 days). The guard
    exists because an in-progress write *looks* orphaned until it commits, so a short threshold on a busy table can delete
    live data. To show the effect, we first plant an uncommitted Parquet file in the table's `data/` folder, the kind of
    file a crashed writer leaves behind.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    orphan_btn = mo.ui.run_button(label="▶ Plant an orphan, then remove orphan files", kind="warn")
    orphan_btn
    return (orphan_btn,)


@app.cell
def _(TABLE, catalog, execute, mo, orphan_btn, set_maint, table_uuid):
    mo.stop(not orphan_btn.value, mo.md("_Click the button to run this step._"))

    # Simulate a crashed writer: a file under data/ that no snapshot references.
    _tbl = catalog.load_table("shop.sensor_readings")
    _orphan = f"{_tbl.location()}/data/orphan-from-crashed-writer.parquet"
    with _tbl.io.new_output(_orphan).create(overwrite=True) as _f:
        _f.write(b"PAR1 not a real parquet file PAR1")

    _result = execute(
        "SET SESSION iceberg.remove_orphan_files_min_retention = '0s'",
        f"ALTER TABLE {TABLE} EXECUTE remove_orphan_files(retention_threshold => '0s')",
    )
    set_maint(lambda log: {**log, "orphans": {"uuid": table_uuid, "result": dict(_result), "planted": _orphan}})
    return


@app.cell(hide_code=True)
def _(maint_log, mo, pd, ran, show):
    if ran("orphans"):
        _o = maint_log["orphans"]
        _out = mo.vstack(
            [
                mo.callout(
                    mo.md(
                        f"**Orphan file removal complete.** Planted `…/{_o['planted'].rsplit('/', 2)[-2]}/{_o['planted'].rsplit('/', 1)[-1]}`; "
                        f"Trino deleted **{_o['result'].get('deleted_files_count', '?')}** file(s)."
                    ),
                    kind="success",
                ),
                show(pd.DataFrame([{"metric": k, "value": v} for k, v in _o["result"].items()])),
                mo.md(
                    "The 20 original tiny files are already gone: `expire_snapshots` deleted them in Step 9. "
                    "Orphan removal catches what expiry can't."
                ),
            ]
        )
    else:
        _out = mo.callout("Orphan removal hasn't run yet.", kind="neutral")
    _out
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 11 — Partition evolution

    Add time-based partitioning so future reads can skip irrelevant data. This is a metadata-only change:
    new inserts are organized by day, and old data keeps its original layout, with no rewrite.
    """)
    return


@app.cell
def _(TABLE, execute, sql, time_before):
    execute(f"ALTER TABLE {TABLE} SET PROPERTIES partitioning = ARRAY['day(reading_time)']")
    show_create = sql(f"SHOW CREATE TABLE {TABLE}").iloc[0, 0]
    _ = time_before
    return (show_create,)


@app.cell(hide_code=True)
def _(mo, show_create):
    mo.vstack(
        [
            mo.callout(mo.md("Partition evolution applied: **`day(reading_time)`**."), kind="success"),
            mo.md("Verify with `SHOW CREATE TABLE iceberg.shop.sensor_readings`:"),
            mo.plain_text(show_create),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 12 — Verify across engines with PyIceberg

    PyIceberg loads the same table from Polaris and confirms every maintenance change is visible.
    """)
    return


@app.cell
def _(catalog, maint_log, show_create):
    table = catalog.load_table("shop.sensor_readings")
    pyiceberg_view = {
        "snapshots": len(table.history()),
        "spec": str(table.spec()),
        "schema": str(table.schema()),
        "rows": len(table.scan().to_arrow()),
    }
    _ = (maint_log, show_create)
    return (pyiceberg_view,)


@app.cell(hide_code=True)
def _(mo, pyiceberg_view):
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(pyiceberg_view["snapshots"], label="Snapshots", caption="table.history()", bordered=True),
                    mo.stat(pyiceberg_view["rows"], label="Rows", caption="table.scan()", bordered=True),
                ],
                widths="equal",
            ),
            mo.hstack(
                [
                    mo.vstack([mo.md("**Partition spec**"), mo.plain_text(pyiceberg_view["spec"])]),
                    mo.vstack([mo.md("**Schema**"), mo.plain_text(pyiceberg_view["schema"])]),
                ],
                widths="equal",
                align="start",
            ),
            mo.callout(
                "Trino did the maintenance, Polaris stored the metadata, and PyIceberg sees the changes instantly. Single source of truth.",
                kind="success",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 13 — Table health report

    A small function that turns the metadata counts into recommendations. We run it on this lab's table and on two
    shared tables. If `shop.orders` or `earthquakes.events` is missing, the next cell creates a small sample
    (it reads them only and never runs maintenance on them).
    """)
    return


@app.cell(hide_code=True)
def _(execute, sql, stack_ok):
    assert stack_ok
    # Shared tables: create only if missing, insert only if empty. Never dropped here.
    execute(
        "CREATE SCHEMA IF NOT EXISTS iceberg.shop WITH (location = 's3://warehouse/polaris_warehouse/shop')",
        """CREATE TABLE IF NOT EXISTS iceberg.shop.orders (
            order_id BIGINT, customer_id BIGINT, order_date DATE, status VARCHAR, total_amount DECIMAL(10, 2)
        ) WITH (format = 'PARQUET')""",
    )
    if int(sql("SELECT count(*) AS n FROM iceberg.shop.orders")["n"].iloc[0]) == 0:
        execute(
            """INSERT INTO iceberg.shop.orders VALUES
            (1001, 1, DATE '2024-01-10', 'shipped', 1349.97), (1002, 2, DATE '2024-01-12', 'shipped', 89.98),
            (1003, 3, DATE '2024-01-15', 'delivered', 449.99), (1004, 1, DATE '2024-01-20', 'delivered', 59.98),
            (1005, 5, DATE '2024-02-01', 'shipped', 1299.99), (1006, 7, DATE '2024-02-05', 'processing', 199.99),
            (1007, 10, DATE '2024-02-10', 'shipped', 639.98), (1008, 4, DATE '2024-02-14', 'delivered', 129.98),
            (1009, 8, DATE '2024-02-20', 'shipped', 399.99), (1010, 6, DATE '2024-03-01', 'processing', 89.99),
            (1011, 12, DATE '2024-03-05', 'shipped', 1749.97), (1012, 15, DATE '2024-03-10', 'delivered', 49.99),
            (1013, 14, DATE '2024-03-15', 'processing', 269.98), (1014, 9, DATE '2024-03-20', 'shipped', 109.99),
            (1015, 20, DATE '2024-03-25', 'delivered', 529.98)"""
        )

    execute(
        "CREATE SCHEMA IF NOT EXISTS iceberg.earthquakes",
        """CREATE TABLE IF NOT EXISTS iceberg.earthquakes.events (
            earthquake_id VARCHAR, magnitude DOUBLE, place VARCHAR,
            event_time TIMESTAMP(6) WITH TIME ZONE, updated_time TIMESTAMP(6) WITH TIME ZONE,
            longitude DOUBLE, latitude DOUBLE, depth_km DOUBLE, tsunami BOOLEAN, event_type VARCHAR,
            title VARCHAR, status VARCHAR, magnitude_type VARCHAR, significance BIGINT, felt_reports BIGINT,
            alert_level VARCHAR, url VARCHAR
        )""",
    )
    quakes_sampled = int(sql("SELECT count(*) AS n FROM iceberg.earthquakes.events")["n"].iloc[0]) == 0
    if quakes_sampled:
        execute(
            """INSERT INTO iceberg.earthquakes.events VALUES
            ('sample01', 4.6, '35 km SW of Hualien City, Taiwan', TIMESTAMP '2026-11-04 03:12:44 UTC', TIMESTAMP '2026-11-04 04:01:10 UTC', 121.3, 23.8, 18.2, false, 'earthquake', 'M 4.6 - 35 km SW of Hualien City, Taiwan', 'reviewed', 'mb', 326, 12, NULL, 'https://earthquake.usgs.gov/earthquakes/eventpage/sample01'),
            ('sample02', 2.1, '8 km NE of Ridgecrest, CA', TIMESTAMP '2026-11-04 05:40:02 UTC', TIMESTAMP '2026-11-04 05:52:31 UTC', -117.6, 35.7, 7.9, false, 'earthquake', 'M 2.1 - 8 km NE of Ridgecrest, CA', 'automatic', 'ml', 68, NULL, NULL, 'https://earthquake.usgs.gov/earthquakes/eventpage/sample02'),
            ('sample03', 5.3, 'Kermadec Islands region', TIMESTAMP '2026-11-04 09:03:19 UTC', TIMESTAMP '2026-11-04 10:15:00 UTC', -177.9, -29.6, 35.0, false, 'earthquake', 'M 5.3 - Kermadec Islands region', 'reviewed', 'mww', 432, 3, 'green', 'https://earthquake.usgs.gov/earthquakes/eventpage/sample03'),
            ('sample04', 1.4, '12 km S of Volcano, Hawaii', TIMESTAMP '2026-11-04 12:27:51 UTC', TIMESTAMP '2026-11-04 12:30:05 UTC', -155.2, 19.3, 2.1, false, 'earthquake', 'M 1.4 - 12 km S of Volcano, Hawaii', 'automatic', 'md', 30, NULL, NULL, 'https://earthquake.usgs.gov/earthquakes/eventpage/sample04'),
            ('sample05', 3.2, '20 km W of Anchorage, Alaska', TIMESTAMP '2026-11-04 18:44:09 UTC', TIMESTAMP '2026-11-04 19:02:44 UTC', -150.3, 61.2, 41.5, false, 'earthquake', 'M 3.2 - 20 km W of Anchorage, Alaska', 'reviewed', 'ml', 158, 25, NULL, 'https://earthquake.usgs.gov/earthquakes/eventpage/sample05')"""
        )
    shared_ready = True
    return quakes_sampled, shared_ready


@app.cell(hide_code=True)
def _(mo, quakes_sampled):
    mo.callout(
        mo.md(
            "`earthquakes.events` was missing, so a **5-row sample** with the dlt pipeline's columns was created. "
            "For real data run the pipeline: `podman compose run --rm dlt-earthquakes` (or `docker compose …`)."
        ),
        kind="warn",
    ) if quakes_sampled else mo.md("")
    return


@app.cell
def _(catalog, pd, sql):
    def table_health(table_name):
        t = catalog.load_table(table_name)
        ns, tbl = table_name.split(".")
        fc = int(sql(f'SELECT count(*) AS cnt FROM iceberg.{ns}."{tbl}$files"')["cnt"].iloc[0])
        sc = int(sql(f'SELECT count(*) AS cnt FROM iceberg.{ns}."{tbl}$snapshots"')["cnt"].iloc[0])

        status = "HEALTHY"
        recommendations = []
        if fc > 10:
            status = "NEEDS MAINTENANCE"
            recommendations.append(f"COMPACT: {fc} data files (run optimize)")
        if sc > 5:
            status = "NEEDS MAINTENANCE"
            recommendations.append(f"EXPIRE: {sc} snapshots (run expire_snapshots)")

        return {
            "table": table_name,
            "status": status,
            "snapshots": sc,
            "data_files": fc,
            "partition_spec": str(t.spec()).replace("\n", " "),
            "recommendations": "; ".join(recommendations) or "none",
        }

    def health_report(tables):
        return pd.DataFrame([table_health(t) for t in tables])

    return (health_report,)


@app.cell
def _(health_report, maint_log, pyiceberg_view, shared_ready):
    health = health_report(["shop.sensor_readings", "shop.orders", "earthquakes.events"])
    _ = (maint_log, pyiceberg_view, shared_ready)
    return (health,)


@app.cell(hide_code=True)
def _(health, mo, show):
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(
                        r.status,
                        label=r.table,
                        caption=f"{r.data_files} files · {r.snapshots} snapshots",
                        bordered=True,
                    )
                    for r in health.itertuples()
                ],
                widths="equal",
            ),
            show(health),
            mo.md(
                "_Click the maintenance buttons above and this report refreshes. "
                "`sensor_readings` turns HEALTHY once it's compacted and its snapshots are expired._"
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
                1. Every small write is a file **and** a snapshot; reads pay for each file with an S3 GET and a split
                2. `optimize` rewrites small files into large ones, and is itself a new snapshot
                3. `expire_snapshots` drops old snapshots and deletes data files only they referenced (guarded by a 7-day minimum)
                4. `remove_orphan_files` deletes files no metadata references, such as leftovers from failed writes
                5. Partition evolution is metadata-only: new data uses the new spec, and old files are not rewritten
                6. Maintenance from any engine is visible to every engine through Polaris
                """
            ),
            "Exercises": mo.md(
                """
                1. **Scale the test** — Insert 50 more rows (one at a time) into `sensor_readings`, then compare query time before and after `optimize`.
                2. **Run the full cycle** on `earthquakes.events` — optimize → expire → orphan removal. Report the before/after metrics.
                   (That table is shared with Lab 4; try it on a copy first: `CREATE TABLE iceberg.earthquakes.events_copy AS SELECT * FROM iceberg.earthquakes.events`.)
                3. **Compare `EXPLAIN ANALYZE`** output before and after compaction (the plans are in Steps 4 and 7). How many "splits" does Trino process in each case?
                4. **Test partition pruning** — After adding day-based partitioning, insert rows for 3 different days. Then `EXPLAIN` a query with
                   `WHERE reading_time > TIMESTAMP '...'` and confirm that partition pruning appears.
                5. **Challenge:** Extend `table_health()` so it returns a maintenance recommendation: "COMPACT" if file_count > 10,
                   "EXPIRE" if snapshot_count > 5, "CLEAN" if appropriate, or "HEALTHY" if everything looks good. Also report the
                   total data size and output the report as JSON.
                """
            ),
            "Run it from the Trino CLI": mo.md(
                """
                ```bash
                podman exec -e TRINO_PASSWORD=admin123 -it trino \\
                  trino --server https://localhost:8443 --user admin --password --insecure
                # (or docker exec …)
                ```

                ```sql
                SET SESSION iceberg.expire_snapshots_min_retention = '0s';
                SET SESSION iceberg.remove_orphan_files_min_retention = '0s';
                ALTER TABLE iceberg.shop.sensor_readings EXECUTE optimize;
                ALTER TABLE iceberg.shop.sensor_readings EXECUTE expire_snapshots(retention_threshold => '1m');
                ALTER TABLE iceberg.shop.sensor_readings EXECUTE remove_orphan_files(retention_threshold => '1m');
                ```
                """
            ),
            "Next lab": mo.md(
                "**Lab 10 — Time Travel** queries old snapshots. Try it before and after expiring snapshots here, and see what you lose."
            ),
        },
        multiple=True,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    **Congratulations!** You've seen firsthand how small-file accumulation degrades performance and how Iceberg's
    maintenance operations fix it, all coordinated through Polaris.
    """)
    return


if __name__ == "__main__":
    app.run()
