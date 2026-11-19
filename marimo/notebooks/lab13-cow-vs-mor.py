import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 13 — Copy-on-Write vs Merge-on-Read")


@app.cell(hide_code=True)
def _():
    import os
    import time

    import marimo as mo
    import pandas as pd
    import pyarrow as pa
    import pyarrow.compute as pc
    import requests
    import urllib3
    from pyiceberg.catalog import load_catalog
    from pyiceberg.expressions import In
    from sqlalchemy import create_engine, text

    urllib3.disable_warnings()

    TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
    POLARIS = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8181"
    POLARIS_HEALTH = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8182/q/health"
    S3_ENDPOINT = f"http://{os.environ.get('S3_HOST', 'localhost')}:4566"
    CATALOG_NAME = "polaris_warehouse"
    SCHEMA = "shop"
    COW = "orders_cow"
    MOR = "orders_mor"
    UPDATED_IDS = ["ORD001", "ORD003", "ORD005", "ORD007", "ORD009"]
    DELETED_IDS = ["ORD012", "ORD014", "ORD015"]

    trino = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (
        CATALOG_NAME,
        COW,
        DELETED_IDS,
        In,
        MOR,
        POLARIS,
        POLARIS_HEALTH,
        S3_ENDPOINT,
        SCHEMA,
        UPDATED_IDS,
        load_catalog,
        mo,
        pa,
        pc,
        pd,
        requests,
        text,
        time,
        trino,
    )


@app.cell(hide_code=True)
def _(SCHEMA, pd, text, trino):
    CONTENT = {0: "DATA", 1: "POSITION_DELETES", 2: "EQUALITY_DELETES"}

    def run_sql(statement):
        """Execute one Trino statement and wait for it to finish."""
        with trino.connect() as conn:
            result = conn.execute(text(statement))
            return result.fetchall() if result.returns_rows else None

    def query(sql):
        with trino.connect() as conn:
            return pd.read_sql(text(sql), conn)

    def list_files(table):
        df = query(
            f'SELECT file_path, content, record_count, file_size_in_bytes FROM iceberg.{SCHEMA}."{table}$files"'
        )
        df["content"] = df["content"].map(CONTENT)
        df["file"] = df["file_path"].str.rsplit("/", n=1).str[-1]
        return df

    def file_lineage(before, after):
        """Label every file as kept, removed or added between two $files listings."""
        old, new = set(before["file_path"]), set(after["file_path"])
        rows = [dict(r, status="kept") for r in after[after["file_path"].isin(old)].to_dict("records")]
        rows += [dict(r, status="added") for r in after[~after["file_path"].isin(old)].to_dict("records")]
        rows += [dict(r, status="removed") for r in before[~before["file_path"].isin(new)].to_dict("records")]
        return pd.DataFrame(rows)[["status", "content", "file", "record_count", "file_size_in_bytes"]]

    def snapshots_of(table):
        df = query(
            f'SELECT snapshot_id, operation, committed_at, summary FROM iceberg.{SCHEMA}."{table}$snapshots" ORDER BY committed_at'
        )
        keys = ["added-data-files", "deleted-data-files", "added-delete-files", "added-records", "deleted-records", "added-files-size"]
        for k in keys:
            df[k] = df["summary"].map(lambda s, k=k: (s or {}).get(k, ""))
        df["engine"] = df["summary"].map(lambda s: (s or {}).get("engine-name", "pyiceberg"))
        return df.drop(columns=["summary"])

    return file_lineage, list_files, query, run_sql, snapshots_of


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar([mo.md("### Lab 13\n**Copy-on-Write vs Merge-on-Read**"), mo.outline()])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 13 — Copy-on-Write vs Merge-on-Read

                **Level:** 5 (Advanced) &nbsp;|&nbsp; **Time:** 30 minutes

                **Goal:** understand the two row-level operation modes in Iceberg. **Copy-on-Write (CoW)** rewrites
                entire files on mutation, while **Merge-on-Read (MoR)** writes small delete files that are merged at
                read time. You will run the same UPDATE and DELETE on two identical tables and compare the files,
                the metadata and the timings.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Create `iceberg.shop.orders_cow` and `iceberg.shop.orders_mor` with 15 identical orders
                    2. Update 5 orders in each table and compare which files were kept, rewritten or added
                    3. Time the same aggregation on both tables
                    4. Delete 3 orders and look for delete files
                    5. *(Optional)* Compact the MoR table and see the delete files disappear
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(CATALOG_NAME, POLARIS, POLARIS_HEALTH, S3_ENDPOINT, load_catalog, mo, requests, run_sql):
    def _reachable(url):
        try:
            return requests.get(url, timeout=5).ok
        except requests.RequestException:
            return False

    def _trino_ok():
        try:
            return run_sql("SELECT 1") == [(1,)]
        except Exception:
            return False

    _polaris_ok = _reachable(POLARIS_HEALTH)
    _s3_ok = _reachable(f"{S3_ENDPOINT}/_localstack/health")
    _trino_up = _trino_ok()
    mo.stop(
        not (_polaris_ok and _s3_ok and _trino_up),
        mo.callout(
            mo.md(
                f"""
                **The lab stack isn't reachable.**
                Trino: {"up" if _trino_up else "**down**"} &nbsp;·&nbsp;
                Polaris: {"up" if _polaris_ok else "**down**"} &nbsp;·&nbsp;
                LocalStack S3: {"up" if _s3_ok else "**down**"}

                Start it with `podman compose --profile marimo up -d` (or `docker compose --profile marimo up -d`),
                then re-run this cell.
                """
            ),
            kind="danger",
        ),
    )

    # PyIceberg with vended credentials: used for drops, table properties and the Copy-on-Write writes.
    catalog = load_catalog(
        "polaris_lab13",
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
    _version = run_sql("SELECT node_version FROM system.runtime.nodes")[0][0]

    mo.hstack(
        [
            mo.stat("Healthy", label="Trino", caption=f"version {_version}", bordered=True),
            mo.stat("Healthy", label="Polaris", caption="REST catalog", bordered=True),
            mo.stat("Healthy", label="LocalStack", caption="S3", bordered=True),
        ],
        widths="equal",
    )
    return (catalog,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Concepts

    When you run an UPDATE or DELETE on an Iceberg table, the engine must reconcile the change with
    **immutable** Parquet data files. Iceberg supports two strategies:

    | Mode | What happens on write | What happens on read | Best for |
    |------|----------------------|---------------------|----------|
    | **Copy-on-Write (CoW)** | Rewrites the entire affected data file with changes applied | Reads clean, compacted files directly | Read-heavy workloads |
    | **Merge-on-Read (MoR)** | Writes a small *delete file* (position or equality deletes) alongside the original data | Merges original data with delete files at query time | Write-heavy workloads |

    **Key point:** the choice is a classic **write-amplification vs read-amplification** trade-off.
    Pick the mode that matches your workload.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "Copy-on-Write": mo.mermaid(
                """
                flowchart LR
                    subgraph B["Before UPDATE"]
                        D1["data-001.parquet<br/>row 1: Alice 10<br/>row 2: Bob 20<br/>row 3: Carol 30"]
                    end
                    subgraph A["After UPDATE row 1"]
                        D2["data-002.parquet (new)<br/>row 1: Alice 99<br/>row 2: Bob 20<br/>row 3: Carol 30"]
                    end
                    D1 -- "rewrite whole file" --> D2
                    D1 -. "removed from snapshot" .-> X(("✗"))
                """
            ),
            "Merge-on-Read": mo.mermaid(
                """
                flowchart LR
                    subgraph B["Before UPDATE"]
                        D1["data-001.parquet<br/>row 1: Alice 10<br/>row 2: Bob 20<br/>row 3: Carol 30"]
                    end
                    subgraph A["After UPDATE row 1"]
                        D1b["data-001.parquet (unchanged)"]
                        DEL["delete-001.parquet (tiny)<br/>position delete: row 1"]
                        D3["data-003.parquet (new value)<br/>row 1: Alice 99"]
                    end
                    D1 -- "keep" --> D1b
                    D1 -- "write delete" --> DEL
                    D1 -- "write new row" --> D3
                    D1b & DEL & D3 --> R["Reader merges all 3 files"]
                """
            ),
            "Table properties": mo.md(
                """
                The mode is a per-table Iceberg property, separately for each kind of row-level operation:

                ```sql
                -- For deletes
                'write.delete.mode' = 'copy-on-write'   -- or 'merge-on-read'
                -- For updates
                'write.update.mode' = 'copy-on-write'   -- or 'merge-on-read'
                -- For merge operations
                'write.merge.mode'  = 'copy-on-write'   -- or 'merge-on-read'
                ```

                Because the properties live in the table metadata in **Polaris**, every engine that honours them
                (Spark, Flink, …) applies the same strategy. Engine support differs, though, and this lab shows how.
                """
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part A — Setup: two identical tables

    ### Step 1 & 2 — Create the CoW and MoR orders tables

    The lab owns `orders_cow` and `orders_mor`, so it drops and recreates them on every run to give a clean history.
    The drop goes through PyIceberg because Polaris refuses Trino's `DROP TABLE`: Trino always asks for a
    *purge*, and this catalog has `DROP_WITH_PURGE_ENABLED` off.

    The lab exercise creates the tables with Trino `WITH (write_delete_mode = …, write_update_mode = …)`.
    The cell below tries exactly that first, then falls back if this Trino version rejects the properties.
    """)
    return


@app.cell
def _(COW, MOR, SCHEMA, catalog, run_sql):
    _columns = """
      order_id VARCHAR,
      customer_id VARCHAR,
      product VARCHAR,
      quantity INT,
      price DECIMAL(10,2),
      order_date TIMESTAMP(6) WITH TIME ZONE
    """
    MODES = {COW: "copy-on-write", MOR: "merge-on-read"}

    run_sql(f"CREATE SCHEMA IF NOT EXISTS iceberg.{SCHEMA} WITH (location = 's3://warehouse/polaris_warehouse/{SCHEMA}')")
    ddl_outcome = {}
    for _table, _mode in MODES.items():
        if catalog.table_exists(f"{SCHEMA}.{_table}"):
            catalog.drop_table(f"{SCHEMA}.{_table}")  # catalog drop only; old files stay in S3

        try:
            # What the lab teaches: set the mode in Trino DDL
            run_sql(f"""
                CREATE TABLE iceberg.{SCHEMA}.{_table} ({_columns})
                WITH (
                  write_delete_mode = '{_mode}',
                  write_update_mode = '{_mode}'
                )
            """)
            ddl_outcome[_table] = "Trino DDL accepted the write modes"
        except Exception as _e:
            # Trino 4xx: these are not Trino table properties → plain DDL, then set the Iceberg properties directly
            ddl_outcome[_table] = str(getattr(_e, "orig", _e)).split("message=")[-1].split(", query_id")[0].strip('"')
            run_sql(f"CREATE TABLE iceberg.{SCHEMA}.{_table} ({_columns})")
            with catalog.load_table(f"{SCHEMA}.{_table}").transaction() as _tx:
                _tx.set_properties({"write.delete.mode": _mode, "write.update.mode": _mode, "write.merge.mode": _mode})
    return MODES, ddl_outcome


@app.cell(hide_code=True)
def _(COW, MODES, MOR, SCHEMA, ddl_outcome, mo, query):
    def _props(table):
        df = query(f'SELECT key, value FROM iceberg.{SCHEMA}."{table}$properties" ORDER BY key')
        return df[df["key"].str.startswith("write.") & df["key"].str.endswith("mode")]

    _rejected = any("does not exist" in v for v in ddl_outcome.values())
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    "**Trino rejected the `write_*_mode` table properties:**\n\n"
                    f"> {ddl_outcome[COW]}\n\n"
                    "So the cell created the tables with plain DDL and set `write.delete.mode`, `write.update.mode` and "
                    "`write.merge.mode` through PyIceberg. They are now ordinary Iceberg properties in Polaris. "
                    "Trino shows them in the `$properties` metadata table:"
                )
                if _rejected
                else mo.md("Trino accepted the write modes in the DDL."),
                kind="warn" if _rejected else "success",
            ),
            mo.hstack(
                [
                    mo.vstack([mo.md(f"**`{t}`** ({MODES[t]})"), mo.ui.table(_props(t), selection=None, show_column_summaries=False)])
                    for t in (COW, MOR)
                ],
                widths="equal",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 3 — Insert identical data into both tables

    The same 15 orders go into each table:
    """)
    return


@app.cell
def _(COW, MODES, MOR, SCHEMA, run_sql):
    MODES  # run after the tables are created
    _insert_sql = """
        INSERT INTO iceberg.{schema}.{table} VALUES
          ('ORD001', 'C001', 'Wireless Mouse',      2,  29.99, CURRENT_TIMESTAMP),
          ('ORD002', 'C002', 'Mechanical Keyboard', 1,  89.99, CURRENT_TIMESTAMP),
          ('ORD003', 'C001', 'USB-C Hub',           3,  45.00, CURRENT_TIMESTAMP),
          ('ORD004', 'C003', 'Monitor Stand',       1,  79.50, CURRENT_TIMESTAMP),
          ('ORD005', 'C002', 'Webcam HD',           1,  64.99, CURRENT_TIMESTAMP),
          ('ORD006', 'C004', 'Desk Lamp',           2,  34.99, CURRENT_TIMESTAMP),
          ('ORD007', 'C001', 'Mouse Pad XL',        1,  19.99, CURRENT_TIMESTAMP),
          ('ORD008', 'C005', 'USB Microphone',      1, 129.00, CURRENT_TIMESTAMP),
          ('ORD009', 'C003', 'HDMI Cable',          4,  12.99, CURRENT_TIMESTAMP),
          ('ORD010', 'C002', 'Laptop Stand',        1,  54.99, CURRENT_TIMESTAMP),
          ('ORD011', 'C004', 'Wireless Charger',    2,  24.99, CURRENT_TIMESTAMP),
          ('ORD012', 'C005', 'Screen Protector',    3,   9.99, CURRENT_TIMESTAMP),
          ('ORD013', 'C001', 'Bluetooth Speaker',   1,  39.99, CURRENT_TIMESTAMP),
          ('ORD014', 'C003', 'Power Strip',         1,  22.50, CURRENT_TIMESTAMP),
          ('ORD015', 'C004', 'Cable Organizer',     2,  14.99, CURRENT_TIMESTAMP)
    """
    for _table in (COW, MOR):
        run_sql(_insert_sql.format(schema=SCHEMA, table=_table))
    orders_loaded = True
    return (orders_loaded,)


@app.cell
def _(SCHEMA, orders_loaded, query):
    orders_loaded  # run after the insert
    row_counts = query(f"""
        SELECT 'COW' AS mode, COUNT(*) AS rows FROM iceberg.{SCHEMA}.orders_cow
        UNION ALL
        SELECT 'MOR' AS mode, COUNT(*) AS rows FROM iceberg.{SCHEMA}.orders_mor
    """)
    return (row_counts,)


@app.cell(hide_code=True)
def _(mo, row_counts):
    _counts = dict(zip(row_counts["mode"], row_counts["rows"]))
    mo.hstack(
        [
            mo.stat(int(_counts["COW"]), label="orders_cow", caption="rows", bordered=True),
            mo.stat(int(_counts["MOR"]), label="orders_mor", caption="rows", bordered=True),
            mo.stat("Yes" if _counts["COW"] == _counts["MOR"] == 15 else "No", label="Identical?", caption="15 rows each", bordered=True),
        ],
        widths="equal",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part B — Compare write behaviour

    ### Step 4 — File counts before mutations

    Both tables should have the same number of data files at this point; nothing has been mutated yet.
    """)
    return


@app.cell
def _(COW, MOR, SCHEMA, list_files, query, row_counts):
    row_counts  # run after the data is loaded
    files_before = query(f"""
        SELECT 'COW' AS mode, COUNT(*) AS file_count, SUM(file_size_in_bytes) AS total_bytes
        FROM iceberg.{SCHEMA}."orders_cow$files"
        UNION ALL
        SELECT 'MOR' AS mode, COUNT(*) AS file_count, SUM(file_size_in_bytes) AS total_bytes
        FROM iceberg.{SCHEMA}."orders_mor$files"
    """)
    # Keep the full listings so we can tell later which files were kept, removed or added
    cow_files_before = list_files(COW)
    mor_files_before = list_files(MOR)
    files_before
    return cow_files_before, mor_files_before


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 5 — Update the CoW table (timed)

    Update the quantity for 5 orders. In SQL that is:

    ```sql
    UPDATE iceberg.shop.orders_cow
    SET quantity = quantity + 10
    WHERE order_id IN ('ORD001', 'ORD003', 'ORD005', 'ORD007', 'ORD009');
    ```

    Copy-on-Write must **rewrite every data file that contains an affected row**.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            """
            **Trino's Iceberg connector always uses Merge-on-Read for UPDATE, DELETE and MERGE.** It ignores
            `write.update.mode = 'copy-on-write'`: running the UPDATE above on `orders_cow` in Trino writes a
            position-delete file, exactly as on `orders_mor`. Spark honours the property; PyIceberg always uses
            copy-on-write. So the CoW side of this lab writes with **PyIceberg**, which gives the same file-level
            result as Spark. The MoR side uses the Trino SQL unchanged.
            """
        ),
        kind="warn",
    )
    return


@app.cell
def _(COW, In, SCHEMA, UPDATED_IDS, catalog, cow_files_before, pa, pc, time):
    cow_files_before  # run after Step 4 captured the "before" state
    _table = catalog.load_table(f"{SCHEMA}.{COW}")
    _targets = In("order_id", UPDATED_IDS)  # WHERE order_id IN (...)

    _t0 = time.perf_counter()
    _rows = _table.scan(row_filter=_targets).to_arrow()  # read the affected rows
    _qty = _rows.schema.get_field_index("quantity")
    _rows = _rows.set_column(  # SET quantity = quantity + 10
        _qty, _rows.schema.field(_qty), pc.add(_rows["quantity"], pa.scalar(10, pa.int32()))
    )
    _table.overwrite(_rows, overwrite_filter=_targets)  # rewrite affected files + write new rows
    cow_write_time = time.perf_counter() - _t0
    return (cow_write_time,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 6 — Run the same update on the MoR table (timed)

    MoR only writes small delete files plus the new values; the original data file is left untouched.
    """)
    return


@app.cell
def _(MOR, SCHEMA, cow_write_time, run_sql, time):
    cow_write_time  # run after the CoW update
    _t0 = time.perf_counter()
    run_sql(f"""
        UPDATE iceberg.{SCHEMA}.{MOR}
        SET quantity = quantity + 10
        WHERE order_id IN ('ORD001', 'ORD003', 'ORD005', 'ORD007', 'ORD009')
    """)
    mor_write_time = time.perf_counter() - _t0
    return (mor_write_time,)


@app.cell(hide_code=True)
def _(cow_write_time, mo, mor_write_time):
    mo.vstack(
        [
            mo.md("#### Write time comparison"),
            mo.hstack(
                [
                    mo.stat(f"{cow_write_time:.3f} s", label="CoW UPDATE", caption="PyIceberg rewrite", bordered=True),
                    mo.stat(f"{mor_write_time:.3f} s", label="MoR UPDATE", caption="Trino delete file", bordered=True),
                ],
                widths="equal",
            ),
            mo.md(
                "At 15 rows the difference is noise, and here the two writes even use different engines. "
                "**Bytes written** (next step) is the better measure. At production scale, with large Parquet files, "
                "MoR writes are much faster because they avoid rewriting whole files."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 7 — Compare file states after the mutation

    Both tables are listed with the query below, and each file is compared with the Step 4 listing:

    ```sql
    SELECT file_path, content, record_count, file_size_in_bytes
    FROM iceberg.shop."orders_cow$files";   -- and "orders_mor$files"
    ```

    **What to look for**

    - **CoW:** the original data file is **removed** from the snapshot and replaced by newly written files.
    - **MoR:** the original data file is **kept**, with an extra delete file (`POSITION_DELETES` or `EQUALITY_DELETES`) next to it.
    """)
    return


@app.cell
def _(COW, MOR, list_files, mor_write_time):
    mor_write_time  # run after both updates
    cow_files_after = list_files(COW)
    mor_files_after = list_files(MOR)
    return cow_files_after, mor_files_after


@app.cell(hide_code=True)
def _(
    cow_files_after,
    cow_files_before,
    file_lineage,
    mo,
    mor_files_after,
    mor_files_before,
):
    def _panel(title, before, after):
        lineage = file_lineage(before, after)
        added = lineage[lineage["status"] == "added"]
        return mo.vstack(
            [
                mo.md(f"**{title}**"),
                mo.hstack(
                    [
                        mo.stat(int((lineage["status"] == "kept").sum()), label="Kept", bordered=True),
                        mo.stat(int((lineage["status"] == "removed").sum()), label="Removed", bordered=True),
                        mo.stat(int(len(added)), label="Added", bordered=True),
                        mo.stat(f"{int(added['file_size_in_bytes'].sum()):,} B", label="Bytes written", bordered=True),
                    ],
                    widths="equal",
                ),
                mo.ui.table(lineage, selection=None, show_column_summaries=False),
            ]
        )

    mo.hstack(
        [
            _panel("Copy-on-Write: orders_cow", cow_files_before, cow_files_after),
            _panel("Merge-on-Read: orders_mor", mor_files_before, mor_files_after),
        ],
        widths="equal",
        align="start",
    )
    return


@app.cell(hide_code=True)
def _(mo, mor_files_after):
    _has_deletes = (mor_files_after["content"] != "DATA").any()
    mo.callout(
        mo.md(
            "**MoR kept its original data file** and added a delete file plus a small file with the new values. "
            "**CoW removed the original file** and wrote fresh data files instead. Neither table has lost history: "
            "both old states are still reachable through time travel."
            if _has_deletes
            else "No delete files found on the MoR table. Check that the UPDATE in Step 6 ran."
        ),
        kind="success" if _has_deletes else "warn",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part C — Compare read performance

    ### Step 8 & 9 — The same aggregation on both tables (timed)

    The CoW table reads clean files with no merge overhead. The MoR table must apply its delete files to the
    data files at query time.
    """)
    return


@app.cell
def _(SCHEMA, cow_files_after, query, time):
    cow_files_after  # run after the updates
    _t0 = time.perf_counter()
    cow_agg = query(f"""
        SELECT
          customer_id,
          COUNT(*) AS order_count,
          SUM(quantity * price) AS total_value
        FROM iceberg.{SCHEMA}.orders_cow
        GROUP BY customer_id
        ORDER BY total_value DESC
    """)
    cow_read_time = time.perf_counter() - _t0
    return cow_agg, cow_read_time


@app.cell
def _(SCHEMA, cow_read_time, query, time):
    cow_read_time  # run after the CoW read
    _t0 = time.perf_counter()
    mor_agg = query(f"""
        SELECT
          customer_id,
          COUNT(*) AS order_count,
          SUM(quantity * price) AS total_value
        FROM iceberg.{SCHEMA}.orders_mor
        GROUP BY customer_id
        ORDER BY total_value DESC
    """)
    mor_read_time = time.perf_counter() - _t0
    return mor_agg, mor_read_time


@app.cell(hide_code=True)
def _(cow_agg, cow_read_time, mo, mor_agg, mor_read_time):
    _same = cow_agg.astype(str).equals(mor_agg.astype(str))
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.vstack(
                        [
                            mo.stat(f"{cow_read_time:.3f} s", label="CoW read", caption="clean files", bordered=True),
                            mo.ui.table(cow_agg, selection=None, show_column_summaries=False),
                        ]
                    ),
                    mo.vstack(
                        [
                            mo.stat(f"{mor_read_time:.3f} s", label="MoR read", caption="data + delete files", bordered=True),
                            mo.ui.table(mor_agg, selection=None, show_column_summaries=False),
                        ]
                    ),
                ],
                widths="equal",
                align="start",
            ),
            mo.callout(
                mo.md(
                    (
                        "**Same answer from both tables.** The storage layout differs, not the data."
                        if _same
                        else "**The results differ.** Re-run the notebook from the top."
                    )
                    + " At this scale the timing difference is tiny. At production scale (millions of rows, hundreds of "
                    "delete files) the MoR read overhead grows with every delete file, so **periodic compaction** "
                    "(`ALTER TABLE ... EXECUTE optimize`) is essential for MoR tables."
                ),
                kind="success" if _same else "danger",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 10 — Delete on both tables and compare

    Delete 3 orders from each table:

    ```sql
    DELETE FROM iceberg.shop.orders_cow WHERE order_id IN ('ORD012', 'ORD014', 'ORD015');
    DELETE FROM iceberg.shop.orders_mor WHERE order_id IN ('ORD012', 'ORD014', 'ORD015');
    ```

    As in Step 5, the CoW delete runs through PyIceberg so that it really is copy-on-write.
    """)
    return


@app.cell
def _(COW, DELETED_IDS, In, MOR, SCHEMA, catalog, mor_read_time, run_sql, time):
    mor_read_time  # run after the reads
    _t0 = time.perf_counter()
    catalog.load_table(f"{SCHEMA}.{COW}").delete(In("order_id", DELETED_IDS))  # CoW: rewrite files without the rows
    cow_del_time = time.perf_counter() - _t0

    _t0 = time.perf_counter()
    run_sql(f"""
        DELETE FROM iceberg.{SCHEMA}.{MOR}
        WHERE order_id IN ('ORD012', 'ORD014', 'ORD015')
    """)  # MoR: write a delete file, originals untouched
    mor_del_time = time.perf_counter() - _t0
    return cow_del_time, mor_del_time


@app.cell
def _(SCHEMA, cow_del_time, query):
    cow_del_time  # run after the deletes
    cow_summary = query(f"""
        SELECT content, COUNT(*) AS cnt, SUM(record_count) AS total_records
        FROM iceberg.{SCHEMA}."orders_cow$files"
        GROUP BY content
    """)
    mor_summary = query(f"""
        SELECT content, COUNT(*) AS cnt, SUM(record_count) AS total_records
        FROM iceberg.{SCHEMA}."orders_mor$files"
        GROUP BY content
    """)
    return cow_summary, mor_summary


@app.cell(hide_code=True)
def _(COW, MOR, cow_del_time, cow_summary, mo, mor_del_time, mor_summary, snapshots_of):
    _labels = {0: "DATA", 1: "POSITION_DELETES", 2: "EQUALITY_DELETES"}

    def _summary_panel(title, seconds, df):
        df = df.assign(content=df["content"].map(_labels)).sort_values("content")
        return mo.vstack(
            [
                mo.stat(f"{seconds:.3f} s", label=title, caption="DELETE time", bordered=True),
                mo.ui.table(df, selection=None, show_column_summaries=False),
            ]
        )

    mo.ui.tabs(
        {
            "Files by content type": mo.vstack(
                [
                    mo.hstack(
                        [
                            _summary_panel("CoW DELETE", cow_del_time, cow_summary),
                            _summary_panel("MoR DELETE", mor_del_time, mor_summary),
                        ],
                        widths="equal",
                        align="start",
                    ),
                    mo.callout(
                        mo.md(
                            "**Notice:** only the MoR table has `POSITION_DELETES` entries. Its `DATA` files still include "
                            "the original 15-row file plus the 5 updated rows, so they hold more records than the table "
                            "returns. The delete files hide the deleted and superseded rows at read time. The CoW `DATA` "
                            "records match the live row count exactly."
                        ),
                        kind="info",
                    ),
                ]
            ),
            "Snapshot metadata": mo.hstack(
                [
                    mo.vstack([mo.md(f"**`{t}$snapshots`**"), mo.ui.table(snapshots_of(t), selection=None, show_column_summaries=False)])
                    for t in (COW, MOR)
                ],
                widths="equal",
                align="start",
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part D — When to use each

    | Aspect | Copy-on-Write | Merge-on-Read |
    |--------|---------------|---------------|
    | Write speed | Slower (rewrites files) | Faster (small delta files) |
    | Read speed | Faster (clean files) | Slower (must merge at read) |
    | Storage | Less (compacted after write) | More (data + delete files) |
    | File count | Fewer (rewritten in place) | More (accumulates deletes) |
    | Best for | Read-heavy workloads | Write-heavy workloads |
    | Compaction need | Low | High (merge deletes back) |
    | Examples | BI dashboards, reporting | IoT ingestion, CDC streams |

    **Rule of thumb:** if your table is read 100x more than it is written, use CoW. If you have frequent
    small updates/deletes and can tolerate slightly slower reads (or run periodic compaction), use MoR.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Optional — Compaction restores read performance

    `optimize` rewrites the MoR table's data files with its delete files applied, so later reads no longer
    need to merge. It rewrites files, so it only runs when you click the button.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    compact_button = mo.ui.run_button(label="Compact orders_mor", kind="warn")
    compact_button
    return (compact_button,)


@app.cell
def _(MOR, SCHEMA, compact_button, list_files, mo, mor_summary, query, run_sql, time):
    mor_summary  # run after Step 10
    mo.stop(
        not compact_button.value,
        mo.callout("Click **Compact orders_mor** to run `ALTER TABLE … EXECUTE optimize`.", kind="neutral"),
    )

    _before = list_files(MOR)
    run_sql(f"ALTER TABLE iceberg.{SCHEMA}.{MOR} EXECUTE optimize")
    _after = list_files(MOR)

    _t0 = time.perf_counter()
    query(f"SELECT customer_id, COUNT(*), SUM(quantity * price) FROM iceberg.{SCHEMA}.{MOR} GROUP BY customer_id")
    _read_after = time.perf_counter() - _t0

    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(_before), label="Files before", caption=f"{int((_before['content'] != 'DATA').sum())} delete files", bordered=True),
                    mo.stat(len(_after), label="Files after", caption=f"{int((_after['content'] != 'DATA').sum())} delete files", bordered=True),
                    mo.stat(f"{_read_after:.3f} s", label="Read after compaction", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.table(_after[["content", "file", "record_count", "file_size_in_bytes"]], selection=None, show_column_summaries=False),
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
                1. Iceberg data files are immutable; row-level changes are either **rewrites** (CoW) or **delete files** (MoR)
                2. CoW pays at write time (write amplification); MoR pays at read time (read amplification)
                3. The mode is set per table and per operation: `write.delete.mode`, `write.update.mode`, `write.merge.mode`
                4. Engines differ: Trino always writes MoR position deletes, PyIceberg always writes CoW, and Spark honours the properties
                5. MoR tables need regular compaction (`ALTER TABLE ... EXECUTE optimize`)
                """
            ),
            "Exercises": mo.md(
                """
                1. **Bulk write benchmark:** insert 50 more rows into both tables, then run 10 separate UPDATE statements
                   on each (updating different rows each time). Compare the total wall-clock time for all writes on CoW vs MoR.
                2. **Query plan analysis:** run `EXPLAIN ANALYZE` on the aggregation query (Steps 8/9) on both tables after
                   all mutations. Look for differences in the plan; MoR may show extra merge or filter stages.
                3. **Compaction restores read performance:** run `ALTER TABLE iceberg.shop.orders_mor EXECUTE optimize`
                   (the button above), then re-run the aggregation query. How do read performance and file layout change
                   compared to before compaction?
                4. **Mixed mode table:** create a table with `write.delete.mode = 'copy-on-write'` and
                   `write.update.mode = 'merge-on-read'`. When would this combination make sense? Test it with DELETEs and
                   UPDATEs and inspect the file metadata. *(Use Spark for the writes; Trino ignores the setting.)*
                5. **Challenge: automated benchmark:** write a script that runs N updates on both tables, captures the wall
                   time for each, and produces a summary. Include a final read query on each table so you can compare
                   total write time + read time for both modes.
                """
            ),
            "Next lab": mo.md(
                "**Lab 14 — Row-Level Operations:** UPDATE, DELETE and MERGE INTO in depth, and how every mutation "
                "becomes a snapshot you can time-travel to."
            ),
        },
        multiple=True,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    **Congratulations!** You now understand the fundamental write-path trade-off in Iceberg. Choosing between CoW
    and MoR is one of the most impactful performance decisions when designing Iceberg tables, and Polaris lets you
    manage these table properties centrally across all engines.
    """)
    return


if __name__ == "__main__":
    app.run()
