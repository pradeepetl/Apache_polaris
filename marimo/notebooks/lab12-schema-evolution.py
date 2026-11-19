import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 12 — Schema Evolution")


@app.cell(hide_code=True)
def _():
    import os

    import marimo as mo
    import pandas as pd
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
    REALM = "POLARIS"

    trino = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (
        CATALOG_NAME,
        POLARIS,
        POLARIS_HEALTH,
        REALM,
        S3_ENDPOINT,
        TRINO_INFO,
        load_catalog,
        mo,
        pd,
        requests,
        text,
        trino,
    )


@app.cell(hide_code=True)
def _(CATALOG_NAME, POLARIS, REALM, mo, pd, requests, text, trino):
    def sql(statement):
        """Run one Trino statement and return the result as a DataFrame (empty for DDL)."""
        with trino.connect() as conn:
            result = conn.execute(text(statement))
            if not result.returns_rows:
                return pd.DataFrame()
            columns = list(result.keys())
            rows = [tuple(r) for r in result.fetchall()]
        df = pd.DataFrame(rows, columns=columns, dtype=object)
        for col in columns:
            # Snapshot IDs are 64-bit; keep them exact by showing them as text.
            if any(isinstance(v, int) and abs(v) > 2**53 for v in df[col] if v is not None):
                df[col] = df[col].map(lambda v: "" if v is None else str(v))
        return df.convert_dtypes()

    def grid(df, **kwargs):
        return mo.ui.table(df, selection=None, show_column_summaries=False, **kwargs)

    def describe():
        """Trino's view of the current schema: column name and type."""
        return sql("DESCRIBE iceberg.shop.user_profiles")[["Column", "Type"]]

    _GREEN, _RED, _YELLOW = "#e3f6e5", "#fde2e1", "#fff4d6"

    def schema_diff(before, after, title_before="Before", title_after="After"):
        """Two DESCRIBE results side by side; added columns green, removed red, retyped yellow."""
        old_types = dict(zip(before["Column"], before["Type"]))
        new_types = dict(zip(after["Column"], after["Type"]))

        def _style(df, colors):
            def style(row_id, column, value):
                color = colors(df.loc[int(row_id), "Column"])
                return {"backgroundColor": color} if color else {}

            return style

        def _before_color(name):
            return _RED if name not in new_types else (_YELLOW if new_types[name] != old_types[name] else None)

        def _after_color(name):
            return _GREEN if name not in old_types else (_YELLOW if new_types[name] != old_types[name] else None)

        return mo.hstack(
            [
                mo.vstack([mo.md(f"**{title_before}**"), grid(before, style_cell=_style(before, _before_color))]),
                mo.vstack([mo.md(f"**{title_after}**"), grid(after, style_cell=_style(after, _after_color))]),
            ],
            widths="equal",
            gap=2,
            align="start",
        )

    def drop_own_table(namespace, table):
        """Drop a table from the Polaris catalog (no purge). Returns True if it existed."""
        token = requests.post(
            f"{POLARIS}/api/catalog/v1/oauth/tokens",
            headers={"Polaris-Realm": REALM},
            data={
                "grant_type": "client_credentials",
                "client_id": "root",
                "client_secret": "s3cr3t",
                "scope": "PRINCIPAL_ROLE:ALL",
            },
            timeout=10,
        ).json()["access_token"]
        resp = requests.delete(
            f"{POLARIS}/api/catalog/v1/{CATALOG_NAME}/namespaces/{namespace}/tables/{table}",
            headers={"Authorization": f"Bearer {token}", "Polaris-Realm": REALM},
            timeout=10,
        )
        if resp.status_code not in (204, 404):
            resp.raise_for_status()
        return resp.status_code == 204

    return describe, drop_own_table, grid, schema_diff, sql


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar(
        [
            mo.md("### Lab 12\n**Schema Evolution**"),
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
                # Lab 12 — Schema Evolution

                **Level:** 4 (Advanced) &nbsp;|&nbsp; **Time:** 25 minutes

                **Goal:** Add, drop, rename and reorder columns in Iceberg tables without rewriting data.
                Demonstrate type promotion and backward compatibility.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Create `iceberg.shop.user_profiles` with 4 columns and 10 rows
                    2. Add columns and see old rows read back as NULL
                    3. Rename, drop, promote and reorder columns, comparing the schema before and after each change
                    4. Inspect the full schema history and the stable column IDs with PyIceberg
                    5. Time-travel to the original snapshot and read it with its original schema
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(POLARIS_HEALTH, TRINO_INFO, mo, requests, sql):
    def _reachable(url, **kwargs):
        try:
            return requests.get(url, timeout=5, **kwargs).ok
        except requests.RequestException:
            return False

    _trino_ok = _reachable(TRINO_INFO, verify=False)
    _polaris_ok = _reachable(POLARIS_HEALTH)
    mo.stop(
        not (_trino_ok and _polaris_ok),
        mo.callout(
            mo.md(
                f"""
                **The lab stack isn't reachable.**
                Trino: {"up" if _trino_ok else "**down**"} &nbsp;·&nbsp; Polaris: {"up" if _polaris_ok else "**down**"}

                Start it with `podman compose --profile marimo up -d` (or `docker compose --profile marimo up -d`),
                then re-run this cell.
                """
            ),
            kind="danger",
        ),
    )

    _version = sql("SELECT node_version FROM system.runtime.nodes").iloc[0, 0]
    stack_ok = True
    mo.hstack(
        [
            mo.stat("Healthy", label="Trino", caption=f"version {_version}", bordered=True),
            mo.stat("Healthy", label="Polaris", caption="REST catalog", bordered=True),
            mo.stat("iceberg.shop", label="Namespace", caption="table: user_profiles", bordered=True),
        ],
        widths="equal",
    )
    return (stack_ok,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Concepts

    Iceberg tracks every column by an internal **column ID**, not by name or position.
    This makes schema changes safe, cheap and non-breaking:

    | Key principle | Why it matters |
    |---------------|----------------|
    | Column IDs (not names/positions) | Renames and reorders never break existing data |
    | Old files readable after changes | New columns are null-filled on read |
    | Type promotion (int → bigint, etc.) | Widen types without rewriting Parquet files |
    | Metadata-only operations | No data rewrite: `ALTER TABLE` is instant |
    | Full schema history | Every version is recorded and queryable |
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md("**How old data files work with a new schema**"),
            mo.mermaid(
                """
                flowchart LR
                    subgraph V1["Schema v1 (columns by ID)"]
                        A1["ID=1 user_id INT"]
                        A2["ID=2 name VARCHAR"]
                        A3["ID=3 email VARCHAR"]
                        A4["ID=4 signup_date DATE"]
                    end
                    subgraph VN["Schema after evolution"]
                        B1["ID=1 user_id INT"]
                        B2["ID=2 full_name VARCHAR<br/>(renamed, same ID)"]
                        B4["ID=4 signup_date DATE"]
                        B5["ID=5 age BIGINT<br/>(added, NULL in old files)"]
                        B6["ID=6 country VARCHAR<br/>(added, NULL in old files)"]
                    end
                    A1 --> B1
                    A2 -- "rename is transparent" --> B2
                    A3 -. "dropped: skipped on read" .-> X(("✕"))
                    A4 --> B4
                """
            ),
            mo.callout(
                mo.md(
                    "Old Parquet files still contain column IDs 1–4. Iceberg maps them to the current schema **by ID**, "
                    "filling NULLs for IDs 5 and 6. **Polaris stores the schema metadata**, so every engine "
                    "(Trino, Spark, PyIceberg) sees the same evolved schema instantly, with no coordination."
                ),
                kind="neutral",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Part A — Build a table

    ### Step 1 — Create the user profiles table

    The notebook runs the SQL for you. To follow along in the Trino CLI instead:

    ```bash
    podman exec -e TRINO_PASSWORD=admin123 -it trino \
      trino --server https://localhost:8443 --user admin --password --insecure
    # or: docker exec ... (same arguments)
    ```

    This lab owns `iceberg.shop.user_profiles`. It drops and recreates the table, so every run starts
    at schema version 0 with a clean snapshot history.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            "**Why not `DROP TABLE` in Trino?** Trino always asks Polaris to *purge* the files, and this "
            "Polaris catalog has `DROP_WITH_PURGE_ENABLED` turned off, so the drop fails with *Failed to drop table*. "
            "The notebook removes the old table through the Iceberg REST API instead (no purge)."
        ),
        kind="neutral",
    )
    return


@app.cell
def _(drop_own_table, mo, sql, stack_ok):
    assert stack_ok
    sql("CREATE SCHEMA IF NOT EXISTS iceberg.shop")
    _dropped = drop_own_table("shop", "user_profiles")  # instead of DROP TABLE IF EXISTS iceberg.shop.user_profiles
    sql(
        """
        CREATE TABLE iceberg.shop.user_profiles (
          user_id INT,
          name VARCHAR,
          email VARCHAR,
          signup_date DATE
        )
        """
    )
    profiles_created = True
    mo.callout(
        mo.md("Table `iceberg.shop.user_profiles` " + ("dropped and recreated." if _dropped else "created.")),
        kind="success",
    )
    return (profiles_created,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 2 — Insert 10 rows of sample data
    """)
    return


@app.cell
def _(profiles_created, sql):
    assert profiles_created
    sql(
        """
        INSERT INTO iceberg.shop.user_profiles VALUES
          (1,  'Alice Johnson',  'alice@example.com',  DATE '2024-01-15'),
          (2,  'Bob Smith',      'bob@example.com',    DATE '2024-02-20'),
          (3,  'Carol White',    'carol@example.com',  DATE '2024-03-10'),
          (4,  'David Brown',    'david@example.com',  DATE '2024-04-05'),
          (5,  'Eve Davis',      'eve@example.com',    DATE '2024-05-12'),
          (6,  'Frank Miller',   'frank@example.com',  DATE '2024-06-18'),
          (7,  'Grace Wilson',   'grace@example.com',  DATE '2024-07-22'),
          (8,  'Henry Taylor',   'henry@example.com',  DATE '2024-08-30'),
          (9,  'Iris Anderson',  'iris@example.com',   DATE '2024-09-14'),
          (10, 'Jack Thomas',    'jack@example.com',   DATE '2024-10-01')
        """
    )
    profiles_loaded = True
    return (profiles_loaded,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 3 — Show the current schema

    You should see 4 columns: `user_id`, `name`, `email`, `signup_date`.
    """)
    return


@app.cell
def _(describe, profiles_loaded, sql):
    assert profiles_loaded
    schema_v1 = describe()  # DESCRIBE iceberg.shop.user_profiles
    original_rows = sql("SELECT * FROM iceberg.shop.user_profiles ORDER BY user_id")
    return original_rows, schema_v1


@app.cell(hide_code=True)
def _(grid, mo, original_rows, schema_v1):
    mo.hstack(
        [
            mo.vstack([mo.md(f"**Original schema ({len(schema_v1)} columns)**"), grid(schema_v1)]),
            mo.vstack([mo.md(f"**Original data ({len(original_rows)} rows)**"), grid(original_rows)]),
        ],
        widths=[1, 2],
        gap=2,
        align="start",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part B — Adding and querying new columns

    ### Step 4 — Add columns

    Add `age` and `country`. This is a **metadata-only** operation: no data files are rewritten.
    """)
    return


@app.cell
def _(describe, schema_v1, sql):
    assert len(schema_v1) == 4
    sql("ALTER TABLE iceberg.shop.user_profiles ADD COLUMN age INT")
    sql("ALTER TABLE iceberg.shop.user_profiles ADD COLUMN country VARCHAR")
    schema_v2 = describe()
    return (schema_v2,)


@app.cell(hide_code=True)
def _(mo, schema_diff, schema_v1, schema_v2):
    mo.vstack(
        [
            schema_diff(schema_v1, schema_v2, "Before: 4 columns", "After ADD COLUMN: 6 columns"),
            mo.callout(mo.md("Added `age` (INT) and `country` (VARCHAR). No data files were rewritten."), kind="success"),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 5 — Query: old rows have NULLs for the new columns

    The original Parquet files don't contain `age` or `country`. Iceberg fills NULLs on read.
    """)
    return


@app.cell
def _(schema_v2, sql):
    assert len(schema_v2) == 6
    rows_after_add = sql("SELECT * FROM iceberg.shop.user_profiles ORDER BY user_id")
    return (rows_after_add,)


@app.cell(hide_code=True)
def _(grid, mo, rows_after_add):
    _nulls = int(rows_after_add["age"].isna().sum())
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"All **{_nulls} of {len(rows_after_add)}** existing rows show NULL for `age` and `country`. "
                    "The original files were **not** rewritten; Iceberg fills the NULLs on read."
                ),
                kind="info",
            ),
            grid(rows_after_add),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 6 — Insert new rows with all columns
    """)
    return


@app.cell
def _(rows_after_add, sql):
    assert len(rows_after_add) == 10
    sql(
        """
        INSERT INTO iceberg.shop.user_profiles VALUES
          (11, 'Karen Lee',     'karen@example.com', DATE '2024-11-05', 29, 'USA'),
          (12, 'Leo Martinez',  'leo@example.com',   DATE '2024-11-10', 34, 'Mexico'),
          (13, 'Mia Garcia',    'mia@example.com',   DATE '2024-12-01', 27, 'Spain')
        """
    )
    new_rows_inserted = True
    return (new_rows_inserted,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 7 — Query: mixed rows

    Rows 1–10 have NULL for the new columns; rows 11–13 have values.
    Old and new data files coexist seamlessly.
    """)
    return


@app.cell
def _(new_rows_inserted, sql):
    assert new_rows_inserted
    mixed_rows = sql(
        """
        SELECT user_id, name, age, country
        FROM iceberg.shop.user_profiles
        ORDER BY user_id
        """
    )
    return (mixed_rows,)


@app.cell(hide_code=True)
def _(grid, mixed_rows, mo):
    _new = mixed_rows["age"].notna()

    def _style(row_id, column, value):
        return {"backgroundColor": "#e3f6e5"} if _new.iloc[int(row_id)] else {}

    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(int((~_new).sum()), label="Old rows", caption="age / country NULL", bordered=True),
                    mo.stat(int(_new.sum()), label="New rows", caption="all columns filled", bordered=True),
                ],
                widths="equal",
            ),
            grid(mixed_rows, style_cell=_style),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part C — Rename, drop, type promotion and reorder

    ### Step 8 — Rename a column

    Rename `name` to `full_name`. The internal column ID stays the same, so old Parquet files
    (which store the data under that ID) are still readable. The rename is purely a metadata change.
    """)
    return


@app.cell
def _(describe, mixed_rows, sql):
    assert len(mixed_rows) == 13
    schema_before_rename = describe()
    sql("ALTER TABLE iceberg.shop.user_profiles RENAME COLUMN name TO full_name")
    schema_after_rename = describe()
    renamed_rows = sql("SELECT user_id, full_name FROM iceberg.shop.user_profiles WHERE user_id <= 3 ORDER BY user_id")
    return renamed_rows, schema_after_rename, schema_before_rename


@app.cell(hide_code=True)
def _(grid, mo, renamed_rows, schema_after_rename, schema_before_rename, schema_diff):
    mo.vstack(
        [
            schema_diff(schema_before_rename, schema_after_rename, "Before", "After RENAME COLUMN name TO full_name"),
            mo.md("**Old data is readable through the new name `full_name`:**"),
            grid(renamed_rows),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 9 — Drop a column

    Drop `email`. The data still exists in the old Parquet files, but Iceberg skips that column ID on read.
    """)
    return


@app.cell
def _(describe, schema_after_rename, sql):
    assert "full_name" in set(schema_after_rename["Column"])
    schema_before_drop = describe()
    sql("ALTER TABLE iceberg.shop.user_profiles DROP COLUMN email")
    schema_after_drop = describe()
    dropped_rows = sql("SELECT * FROM iceberg.shop.user_profiles WHERE user_id <= 3 ORDER BY user_id")
    return dropped_rows, schema_after_drop, schema_before_drop


@app.cell(hide_code=True)
def _(dropped_rows, grid, mo, schema_after_drop, schema_before_drop, schema_diff):
    mo.vstack(
        [
            schema_diff(schema_before_drop, schema_after_drop, "Before", "After DROP COLUMN email"),
            mo.md("**Query result: the `email` column is gone.**"),
            grid(dropped_rows),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 10 — Type promotion

    Widen `age` from INT to BIGINT. This is a safe promotion that needs no data rewrite:
    existing INT values are read as BIGINT transparently.

    **Supported Iceberg type promotions:**

    - `int` to `bigint`
    - `float` to `double`
    - `decimal(P, S)` to `decimal(P', S)` where P' > P (increase precision)
    """)
    return


@app.cell
def _(describe, schema_after_drop, sql):
    assert "email" not in set(schema_after_drop["Column"])
    schema_before_promote = describe()
    sql("ALTER TABLE iceberg.shop.user_profiles ALTER COLUMN age SET DATA TYPE BIGINT")
    schema_after_promote = describe()
    return schema_after_promote, schema_before_promote


@app.cell(hide_code=True)
def _(mo, schema_after_promote, schema_before_promote, schema_diff):
    _age = dict(zip(schema_after_promote["Column"], schema_after_promote["Type"]))["age"]
    mo.vstack(
        [
            schema_diff(schema_before_promote, schema_after_promote, "Before", "After SET DATA TYPE BIGINT"),
            mo.callout(mo.md(f"`age` is now **{_age}**. The existing INT values are read as BIGINT."), kind="success"),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 10b — Reorder columns

    Reordering changes only the display order; the column IDs don't move.
    Trino can place a **new** column with `ADD COLUMN ... FIRST` or `AFTER <col>`, but it has no statement to move an
    existing one (Spark has `ALTER TABLE ... ALTER COLUMN ... AFTER ...`). Here we use PyIceberg's schema API to move
    `country` right after `user_id`. The PyIceberg connection gets its S3 access from Polaris through
    **vended credentials**, so the config has no S3 keys.
    """)
    return


@app.cell
def _(CATALOG_NAME, POLARIS, S3_ENDPOINT, load_catalog):
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
    return (catalog,)


@app.cell
def _(catalog, describe, schema_after_promote):
    assert "bigint" in set(schema_after_promote["Type"])
    schema_before_reorder = describe()
    with catalog.load_table("shop.user_profiles").update_schema() as _update:
        _update.move_after("country", "user_id")
    schema_after_reorder = describe()  # Trino sees the new order immediately, through Polaris
    return schema_after_reorder, schema_before_reorder


@app.cell(hide_code=True)
def _(mo, schema_after_reorder, schema_before_reorder, schema_diff):
    mo.vstack(
        [
            schema_diff(schema_before_reorder, schema_after_reorder, "Before", "After move_after('country', 'user_id')"),
            mo.callout(
                mo.md(
                    "PyIceberg committed the change to Polaris, and Trino's `DESCRIBE` shows the new order right away. "
                    "Same column IDs, same data files."
                ),
                kind="success",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part D — Inspect schema history with PyIceberg

    ### Step 11 — View the schema history

    Iceberg records every schema version. PyIceberg lets us inspect the full history.
    """)
    return


@app.cell
def _(catalog, schema_after_reorder):
    assert len(schema_after_reorder) == 5
    table = catalog.load_table("shop.user_profiles")

    current_schema = table.schema()
    schema_history = {schema_id: schema for schema_id, schema in table.schemas().items()}
    return current_schema, schema_history, table


@app.cell(hide_code=True)
def _(current_schema, grid, mo, pd, schema_history, table):
    _ids = sorted({f.field_id for s in schema_history.values() for f in s.fields})
    _by_id = {sid: {f.field_id: f for f in s.fields} for sid, s in schema_history.items()}
    _matrix = pd.DataFrame(
        [
            {
                "column ID": fid,
                **{
                    f"v{sid}": (
                        f"{_by_id[sid][fid].name} ({_by_id[sid][fid].field_type})" if fid in _by_id[sid] else "—"
                    )
                    for sid in schema_history
                },
            }
            for fid in _ids
        ]
    )
    _changes = {
        0: "CREATE TABLE",
        1: "ADD COLUMN age",
        2: "ADD COLUMN country",
        3: "RENAME name → full_name",
        4: "DROP COLUMN email",
        5: "age INT → BIGINT",
        6: "move country after user_id",
    }
    _list = pd.DataFrame(
        [
            {
                "schema_id": sid,
                "change": _changes.get(sid, ""),
                "columns": ", ".join(f.name for f in s.fields),
                "current": "◀ current" if sid == table.metadata.current_schema_id else "",
            }
            for sid, s in schema_history.items()
        ]
    )
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(schema_history), label="Schema versions", bordered=True),
                    mo.stat(table.metadata.current_schema_id, label="Current schema ID", bordered=True),
                    mo.stat(len(current_schema.fields), label="Columns now", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.tabs(
                {
                    "Schema history": grid(_list),
                    "Column ID × version": grid(_matrix),
                    "Current schema": mo.md(f"```text\n{current_schema}\n```"),
                }
            ),
            mo.md(
                "Read the **Column ID × version** tab row by row: column ID 2 is `name` up to v2 and `full_name` "
                "from v3; ID 3 (`email`) disappears in v4; ID 5 (`age`) changes from `int` to `long` in v5."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 12 — Time travel: query an old snapshot

    Use the snapshot from the **original INSERT** to see the table as it was before any schema changes.
    Trino reads each snapshot with the schema that was current when it was written.
    """)
    return


@app.cell
def _(sql, table):
    assert table is not None
    snapshots_df = sql(
        """
        SELECT snapshot_id, committed_at
        FROM iceberg.shop."user_profiles$snapshots"
        ORDER BY committed_at
        """
    )
    return (snapshots_df,)


@app.cell(hide_code=True)
def _(grid, pd, snapshots_df, table):
    _meta = {
        str(s.snapshot_id): {
            "operation": s.summary.operation.value,
            "schema_id": s.schema_id,
            "total_records": int(s.summary.get("total-records", 0)),
        }
        for s in table.snapshots()
    }
    snapshot_info = pd.concat(
        [snapshots_df, pd.DataFrame([_meta[s] for s in snapshots_df["snapshot_id"]])], axis=1
    )
    # Recent Trino versions commit an empty snapshot for CREATE TABLE; the first INSERT is the first one with rows.
    first_snapshot_id = int(snapshot_info.loc[snapshot_info["total_records"] > 0, "snapshot_id"].iloc[0])
    grid(snapshot_info)
    return first_snapshot_id, snapshot_info


@app.cell
def _(first_snapshot_id, sql):
    time_travel_rows = sql(f"SELECT * FROM iceberg.shop.user_profiles FOR VERSION AS OF {first_snapshot_id}")
    return (time_travel_rows,)


@app.cell(hide_code=True)
def _(first_snapshot_id, grid, mo, time_travel_rows):
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"Snapshot `{first_snapshot_id}` returns **{len(time_travel_rows)} rows** with the original "
                    f"{len(time_travel_rows.columns)}-column schema: `{'`, `'.join(time_travel_rows.columns)}`."
                ),
                kind="success",
            ),
            grid(time_travel_rows),
            mo.callout(
                mo.md(
                    "The snapshot list starts with an **empty snapshot from `CREATE TABLE`** (0 records). "
                    "The notebook picks the first snapshot that has rows: the original INSERT."
                ),
                kind="neutral",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Try it: compare any snapshot with the current table

    Pick a snapshot. Left: what `FOR VERSION AS OF` returns. Right: the table today.
    """)
    return


@app.cell(hide_code=True)
def _(first_snapshot_id, mo, snapshot_info):
    _options = {
        f"{r['committed_at'].strftime('%H:%M:%S')} · {r['operation']} · schema v{r['schema_id']} · {r['total_records']} rows": r[
            "snapshot_id"
        ]
        for _, r in snapshot_info.iterrows()
    }
    snapshot_picker = mo.ui.dropdown(
        _options,
        value=next(k for k, v in _options.items() if v == str(first_snapshot_id)),
        label="Snapshot",
    )
    snapshot_picker
    return (snapshot_picker,)


@app.cell(hide_code=True)
def _(grid, mo, snapshot_picker, sql):
    _old = sql(f"SELECT * FROM iceberg.shop.user_profiles FOR VERSION AS OF {snapshot_picker.value} ORDER BY user_id")
    _now = sql("SELECT * FROM iceberg.shop.user_profiles ORDER BY user_id")
    mo.hstack(
        [
            mo.vstack(
                [
                    mo.md(f"**Snapshot `{snapshot_picker.value}`**: {len(_old)} rows, {len(_old.columns)} columns"),
                    grid(_old) if len(_old) else mo.md(f"_No rows. Columns: `{'`, `'.join(_old.columns)}`_"),
                ]
            ),
            mo.vstack([mo.md(f"**Current table**: {len(_now)} rows, {len(_now.columns)} columns"), grid(_now)]),
        ],
        widths="equal",
        gap=2,
        align="start",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 13 — Verify column ID stability

    The key insight: when we renamed `name` to `full_name`, the internal column ID stayed the same.
    That is why old Parquet files are still perfectly readable: Iceberg matches data to columns **by ID, not by name**.
    """)
    return


@app.cell
def _(catalog, schema_history):
    assert schema_history
    _table = catalog.load_table("shop.user_profiles")
    column_ids = [(field.field_id, field.name, str(field.field_type)) for field in _table.schema().fields]
    original_ids = [(field.field_id, field.name, str(field.field_type)) for field in schema_history[0].fields]
    return column_ids, original_ids


@app.cell(hide_code=True)
def _(column_ids, grid, mo, original_ids, pd):
    _cols = ["ID", "name", "type"]
    _current = {fid: name for fid, name, _ in column_ids}
    _original = {fid: name for fid, name, _ in original_ids}
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.vstack([mo.md("**Schema v0 (original)**"), grid(pd.DataFrame(original_ids, columns=_cols))]),
                    mo.vstack([mo.md("**Current schema**"), grid(pd.DataFrame(column_ids, columns=_cols))]),
                ],
                widths="equal",
                gap=2,
                align="start",
            ),
            mo.callout(
                mo.md(
                    f"**`{_current.get(2)}` has column ID 2, the same ID as the original `{_original.get(2)}`.** "
                    "Iceberg matches data to columns by ID, not by name, so renames are free. "
                    "ID 3 (`email`) is gone, and IDs 5 and 6 are new."
                ),
                kind="success",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part E — Schema evolution summary

    | Operation | SQL | Data rewrite? | How Iceberg handles it |
    |-----------|-----|:-------------:|------------------------|
    | **Add column** | `ALTER TABLE ... ADD COLUMN` | No | New column ID assigned; old files return NULL |
    | **Drop column** | `ALTER TABLE ... DROP COLUMN` | No | Column ID removed from schema; old files skip it |
    | **Rename column** | `ALTER TABLE ... RENAME COLUMN` | No | Same column ID, new name in metadata |
    | **Type promotion** | `ALTER TABLE ... ALTER COLUMN ... SET DATA TYPE` | No | Old values read through the wider type |
    | **Reorder columns** | Spark: `ALTER TABLE ... ALTER COLUMN ... AFTER ...`; Trino: `ADD COLUMN ... AFTER` (new columns only); PyIceberg: `move_after()` | No | Column IDs unchanged; display order updated |

    All operations are **metadata-only** and take effect instantly across every engine
    connected through the Polaris catalog.
    """)
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
                1. Iceberg identifies columns by **ID**, so renames, drops and reorders never touch data files
                2. Added columns read as NULL from old files; new files carry real values
                3. Safe type promotions (`int → bigint`, `float → double`, wider decimals) need no rewrite
                4. Every change creates a new schema version; old snapshots keep the schema they were written with
                5. Polaris stores the schema, so Trino and PyIceberg see each change immediately
                """
            ),
            "Exercises": mo.md(
                """
                1. **Add a nested column:** add a column `address` of type `ROW(street VARCHAR, city VARCHAR, zip VARCHAR)`.
                   Insert a row with address data and query it.
                2. **Multiple renames:** rename `full_name` to `display_name`, then back to `full_name`.
                   Verify the column ID stays the same throughout.
                3. **Schema impact on partitioning:** add a `region` column, then set the table partitioning to include `region`.
                   Insert rows with different regions and verify partition pruning with `EXPLAIN`.
                4. **Type promotion chain:** create a new table with a `score DECIMAL(5,2)` column. Insert data, promote to
                   `DECIMAL(10,2)`, insert more data, and verify all rows are queryable.
                5. **Challenge: five-evolution verification.** Evolve the `user_profiles` schema 5 additional times
                   (add columns, rename, drop, promote types). After each change, insert at least one row. Then write a
                   PyIceberg script that loads every historical snapshot and verifies each one is still queryable by
                   printing the row count and column names per snapshot.
                """
            ),
            "Next lab": mo.md(
                """
                **Lab 13 — Copy-on-Write vs Merge-on-Read:** see how Iceberg writes updates and deletes,
                and what each strategy costs at read time.

                **Congratulations!** You have performed safe, metadata-only schema evolution on Iceberg tables
                and verified backward compatibility across all historical snapshots.
                """
            ),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
