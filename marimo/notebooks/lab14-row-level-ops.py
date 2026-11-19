import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 14 — Row-Level Operations")


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
    POLARIS = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8181"
    POLARIS_HEALTH = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8182/q/health"
    S3_ENDPOINT = f"http://{os.environ.get('S3_HOST', 'localhost')}:4566"
    CATALOG_NAME = "polaris_warehouse"
    SCHEMA = "shop"
    CUSTOMERS = f"iceberg.{SCHEMA}.customers"
    STAGING = f"iceberg.{SCHEMA}.customers_staging"

    trino = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (
        CATALOG_NAME,
        CUSTOMERS,
        POLARIS,
        POLARIS_HEALTH,
        S3_ENDPOINT,
        SCHEMA,
        STAGING,
        load_catalog,
        mo,
        pd,
        requests,
        text,
        trino,
    )


@app.cell(hide_code=True)
def _(CUSTOMERS, SCHEMA, mo, pd, text, trino):
    def run_sql(statement):
        """Execute one Trino statement and wait for it to finish."""
        with trino.connect() as conn:
            result = conn.execute(text(statement))
            return result.fetchall() if result.returns_rows else None

    def query(sql):
        with trino.connect() as conn:
            df = pd.read_sql(text(sql), conn)
        if "parent_id" in df:
            df["parent_id"] = df["parent_id"].astype("Int64")  # keep 64-bit IDs exact (no float NaN)
        return df

    def current_snapshot():
        return int(
            run_sql(f'SELECT snapshot_id FROM iceberg.{SCHEMA}."customers$snapshots" ORDER BY committed_at DESC LIMIT 1')[0][0]
        )

    def customers_at(snapshot_id, columns="customer_id, name, email, tier, total_spent"):
        return query(f"SELECT {columns} FROM {CUSTOMERS} FOR VERSION AS OF {snapshot_id} ORDER BY customer_id")

    def before_after(before_id, after_id, title_before="Before", title_after="After"):
        """Two snapshots side by side, with a per-row status column on the 'after' side."""
        before = customers_at(before_id).set_index("customer_id")
        after = customers_at(after_id).set_index("customer_id")
        status = {}
        for cid in before.index.union(after.index):
            if cid not in after.index:
                status[cid] = "DELETED"
            elif cid not in before.index:
                status[cid] = "INSERTED"
            elif not before.loc[cid].astype(str).equals(after.loc[cid].astype(str)):
                status[cid] = "UPDATED"
            else:
                status[cid] = "unchanged"
        before_df = before.reset_index()
        before_df.insert(0, "status", before_df["customer_id"].map(lambda c: "DELETED" if status[c] == "DELETED" else ""))
        after_df = after.reset_index()
        after_df.insert(0, "status", after_df["customer_id"].map(lambda c: "" if status[c] == "unchanged" else status[c]))
        counts = pd.Series(status).value_counts()
        tiles = mo.hstack(
            [
                mo.stat(len(before), label="Rows before", bordered=True),
                mo.stat(len(after), label="Rows after", bordered=True),
                mo.stat(int(counts.get("UPDATED", 0)), label="Updated", bordered=True),
                mo.stat(int(counts.get("INSERTED", 0)), label="Inserted", bordered=True),
                mo.stat(int(counts.get("DELETED", 0)), label="Deleted", bordered=True),
            ],
            widths="equal",
        )
        tables = mo.hstack(
            [
                mo.vstack([mo.md(f"**{title_before}** · snapshot `{before_id}`"), mo.ui.table(before_df, selection=None, show_column_summaries=False, page_size=12)]),
                mo.vstack([mo.md(f"**{title_after}** · snapshot `{after_id}`"), mo.ui.table(after_df, selection=None, show_column_summaries=False, page_size=12)]),
            ],
            widths="equal",
            align="start",
        )
        return mo.vstack([tiles, tables])

    return before_after, current_snapshot, customers_at, query, run_sql


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar([mo.md("### Lab 14\n**Row-Level Operations**"), mo.outline()])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 14 — Row-Level Operations (UPDATE, DELETE, MERGE)

                **Level:** 4 (Intermediate) &nbsp;|&nbsp; **Time:** 30 minutes

                **Goal:** master Iceberg's row-level mutations (UPDATE, DELETE and MERGE INTO) and see how each one
                creates a snapshot you can time-travel to.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Create the Iceberg table `iceberg.shop.customers` with 10 customers
                    2. UPDATE tiers and spend, and compare each change before and after
                    3. DELETE low-activity customers, then recover them with time travel
                    4. MERGE a staging table (upsert) into `customers`
                    5. Walk the snapshot history and build a full diff against the original state

                    This lab uses its own **Iceberg** tables, not the Postgres `postgres.public.customers` table from Lab 2.
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
    _trino_up = _trino_ok()
    mo.stop(
        not (_polaris_ok and _trino_up),
        mo.callout(
            mo.md(
                f"""
                **The lab stack isn't reachable.**
                Trino: {"up" if _trino_up else "**down**"} &nbsp;·&nbsp; Polaris: {"up" if _polaris_ok else "**down**"}

                Start it with `podman compose --profile marimo up -d` (or `docker compose --profile marimo up -d`),
                then re-run this cell.
                """
            ),
            kind="danger",
        ),
    )

    # PyIceberg (vended credentials) is used only to drop this lab's tables on re-runs.
    catalog = load_catalog(
        "polaris_lab14",
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
            mo.stat(CATALOG_NAME, label="Catalog", caption="iceberg.shop", bordered=True),
        ],
        widths="equal",
    )
    return (catalog,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Concepts

    Traditional Hive tables support only INSERT and full-partition overwrite. Iceberg supports **full row-level
    operations** (UPDATE, DELETE and MERGE INTO), and each mutation creates a new **immutable snapshot**.
    That gives you a complete audit trail and the ability to time-travel to any earlier state.

    | Operation | What it does | Snapshot type |
    |-----------|-------------|---------------|
    | **UPDATE** | Modify columns in existing rows that match a condition | `overwrite` |
    | **DELETE** | Remove rows that match a condition | `delete` |
    | **MERGE INTO** | Upsert: update matched rows, insert unmatched rows | `overwrite` |
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "Snapshots in this lab": mo.mermaid(
                """
                flowchart LR
                    S1["Snap: INSERT<br/>10 customers<br/><b>10 rows</b>"] --> S2["Snap: UPDATE<br/>promote to gold<br/><b>10 rows</b>"]
                    S2 --> S3["Snap: UPDATE<br/>loyalty bonus<br/><b>10 rows</b>"]
                    S3 --> S4["Snap: DELETE<br/>removed 3<br/><b>7 rows</b>"]
                    S4 --> S5["Snap: MERGE INTO<br/>3 updated + 2 inserted<br/><b>9 rows</b>"]
                    S5 -. "time travel / rollback<br/>to any earlier snapshot" .-> S1
                """
            ),
            "How MERGE INTO works": mo.vstack(
                [
                    mo.md(
                        """
                        **MERGE INTO** is the most powerful operation. It combines UPDATE and INSERT in a single
                        atomic statement, the *upsert* pattern:

                        - **WHEN MATCHED**: the row already exists in the target table, so update it (or delete it)
                        - **WHEN NOT MATCHED**: the row is new, so insert it

                        This is the standard pattern for incremental data loads.
                        """
                    ),
                    mo.mermaid(
                        """
                        flowchart LR
                            ST["staging row"] --> J{"customer_id<br/>in target?"}
                            J -- "yes + condition" --> U["UPDATE target row"]
                            J -- "yes, condition false" --> K["leave unchanged"]
                            J -- "no" --> I["INSERT new row"]
                            U & K & I --> C["one atomic commit<br/>= one snapshot"]
                        """
                    ),
                ]
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part A — Setup

    ### Step 1 — Create the customers table

    The notebook owns `iceberg.shop.customers` and `iceberg.shop.customers_staging`, so it drops them first and
    every run starts with a clean history. The drop goes through PyIceberg because Polaris rejects Trino's
    purging `DROP TABLE` (`DROP_WITH_PURGE_ENABLED` is off in this catalog).
    """)
    return


@app.cell
def _(CUSTOMERS, SCHEMA, catalog, run_sql):
    for _name in ("customers", "customers_staging"):
        if catalog.table_exists(f"{SCHEMA}.{_name}"):
            catalog.drop_table(f"{SCHEMA}.{_name}")

    run_sql(f"CREATE SCHEMA IF NOT EXISTS iceberg.{SCHEMA} WITH (location = 's3://warehouse/polaris_warehouse/{SCHEMA}')")
    run_sql(f"""
        CREATE TABLE {CUSTOMERS} (
          customer_id VARCHAR,
          name VARCHAR,
          email VARCHAR,
          tier VARCHAR,
          total_spent DECIMAL(10,2),
          signup_date DATE
        )
    """)
    customers_created = True
    return (customers_created,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 2 — Insert 10 customers

    A mix of bronze, silver and gold tiers with varying spend. Some emails have deliberately mixed case;
    Exercise 1 uses them.
    """)
    return


@app.cell
def _(CUSTOMERS, current_snapshot, customers_created, run_sql):
    customers_created  # run after Step 1
    run_sql(f"""
        INSERT INTO {CUSTOMERS} VALUES
          ('C001', 'Alice Johnson',   'Alice.Johnson@example.com',   'gold',   750.00, DATE '2024-01-15'),
          ('C002', 'Bob Smith',       'Bob.Smith@example.com',       'silver', 320.50, DATE '2024-02-20'),
          ('C003', 'Carol Davis',     'CAROL.DAVIS@example.com',     'bronze',  45.00, DATE '2024-03-10'),
          ('C004', 'David Wilson',    'David.Wilson@EXAMPLE.COM',    'silver', 510.75, DATE '2024-04-05'),
          ('C005', 'Eve Martinez',    'Eve.Martinez@example.com',    'gold',   920.00, DATE '2024-05-12'),
          ('C006', 'Frank Brown',     'FRANK.BROWN@example.com',     'bronze',  30.00, DATE '2024-06-18'),
          ('C007', 'Grace Lee',       'Grace.Lee@example.com',       'silver', 275.25, DATE '2024-07-22'),
          ('C008', 'Henry Taylor',    'Henry.Taylor@example.com',    'gold',   680.00, DATE '2024-08-30'),
          ('C009', 'Iris Chen',       'Iris.Chen@example.com',       'bronze',  15.50, DATE '2024-09-14'),
          ('C010', 'Jack Anderson',   'Jack.Anderson@example.com',   'silver', 490.00, DATE '2024-10-01')
    """)
    snap1_id = current_snapshot()  # the snapshot holding the original 10 rows
    return (snap1_id,)


@app.cell
def _(CUSTOMERS, query, snap1_id):
    snap1_id  # run after the insert
    df_initial = query(f"SELECT * FROM {CUSTOMERS} ORDER BY customer_id")
    return (df_initial,)


@app.cell(hide_code=True)
def _(df_initial, mo):
    _tiers = df_initial["tier"].value_counts()
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(df_initial), label="Customers", bordered=True),
                    mo.stat(int(_tiers.get("gold", 0)), label="Gold", bordered=True),
                    mo.stat(int(_tiers.get("silver", 0)), label="Silver", bordered=True),
                    mo.stat(int(_tiers.get("bronze", 0)), label="Bronze", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.table(df_initial, selection=None, show_column_summaries=False),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part B — UPDATE operations

    ### Step 3 — Simple UPDATE: promote high spenders to gold

    Customers who have spent more than $500 deserve the gold tier:
    """)
    return


@app.cell
def _(CUSTOMERS, current_snapshot, run_sql, snap1_id):
    snap1_id  # run after Step 2
    run_sql(f"""
        UPDATE {CUSTOMERS}
        SET tier = 'gold'
        WHERE total_spent > 500 AND tier <> 'gold'
    """)
    snap_promote_id = current_snapshot()
    return (snap_promote_id,)


@app.cell
def _(CUSTOMERS, query, snap_promote_id):
    snap_promote_id  # run after the UPDATE
    df_after_promo = query(f"""
        SELECT customer_id, name, tier, total_spent
        FROM {CUSTOMERS}
        WHERE tier = 'gold'
        ORDER BY customer_id
    """)
    return (df_after_promo,)


@app.cell(hide_code=True)
def _(before_after, df_after_promo, mo, snap1_id, snap_promote_id):
    _david = "C004" in set(df_after_promo["customer_id"])
    mo.vstack(
        [
            before_after(snap1_id, snap_promote_id, "Before UPDATE", "After UPDATE"),
            mo.md(f"**Gold-tier customers now:** {', '.join(df_after_promo['name'])}"),
            mo.callout(
                mo.md(
                    "**David Wilson (C004, $510.75) is now gold**, alongside Alice, Eve and Henry."
                    if _david
                    else "David Wilson (C004) is not gold. Re-run the notebook from the top."
                ),
                kind="success" if _david else "warn",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 4 — Conditional UPDATE: loyalty bonus for gold customers

    Give all gold-tier customers a 10% spending bonus:
    """)
    return


@app.cell
def _(CUSTOMERS, current_snapshot, run_sql, snap_promote_id):
    snap_promote_id  # run after Step 3
    run_sql(f"""
        UPDATE {CUSTOMERS}
        SET total_spent = total_spent * 1.10
        WHERE tier = 'gold'
    """)
    snap_bonus_id = current_snapshot()
    return (snap_bonus_id,)


@app.cell
def _(CUSTOMERS, query, snap_bonus_id):
    snap_bonus_id  # run after the UPDATE
    df_after_bonus = query(f"""
        SELECT customer_id, name, tier, total_spent
        FROM {CUSTOMERS}
        WHERE tier = 'gold'
        ORDER BY customer_id
    """)
    return (df_after_bonus,)


@app.cell(hide_code=True)
def _(before_after, df_after_bonus, mo, snap_bonus_id, snap_promote_id):
    mo.vstack(
        [
            before_after(snap_promote_id, snap_bonus_id, "Before bonus", "After bonus"),
            mo.md("**Gold customers after the loyalty bonus:**"),
            mo.ui.table(df_after_bonus, selection=None, show_column_summaries=False),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 5 — Check the snapshot count

    Every operation creates a snapshot. The lab expects 3 so far: the INSERT and 2 UPDATEs.
    """)
    return


@app.cell
def _(SCHEMA, query, snap_bonus_id):
    snap_bonus_id  # run after Step 4
    snapshots_b = query(f"""
        SELECT
          snapshot_id,
          parent_id,
          operation,
          committed_at
        FROM iceberg.{SCHEMA}."customers$snapshots"
        ORDER BY committed_at
    """)
    return (snapshots_b,)


@app.cell(hide_code=True)
def _(mo, snap1_id, snap_bonus_id, snap_promote_id, snapshots_b):
    _labels = {snap1_id: "Initial 10-row insert", snap_promote_id: "Promoted high spenders to gold", snap_bonus_id: "Applied 10% loyalty bonus"}
    _view = snapshots_b.assign(what_happened=snapshots_b["snapshot_id"].map(lambda s: _labels.get(int(s), "CREATE TABLE (empty)")))
    _extra = len(snapshots_b) - 3
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(snapshots_b), label="Snapshots", bordered=True),
                    mo.stat(3, label="From INSERT + UPDATEs", bordered=True),
                    mo.stat(snap1_id, label="snap1_id", caption="original 10 rows", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.table(_view, selection=None, show_column_summaries=False),
            mo.callout(
                mo.md(
                    f"**Why {len(snapshots_b)} and not 3?** Trino's `CREATE TABLE` commits an empty `append` snapshot. "
                    "So *the first snapshot* is not the one with your data. The notebook records each snapshot ID right after "
                    "the statement that created it (`snap1_id`, `snap_promote_id`, `snap_bonus_id`) instead of picking by position."
                )
                if _extra
                else mo.md("Exactly 3 snapshots: the INSERT and the two UPDATEs."),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part C — DELETE operations

    ### Step 6 — DELETE low-activity customers

    Remove customers who have spent less than $50:
    """)
    return


@app.cell
def _(CUSTOMERS, current_snapshot, run_sql, snapshots_b):
    snapshots_b  # run after Step 5
    rows_before_delete = int(run_sql(f"SELECT COUNT(*) FROM {CUSTOMERS}")[0][0])
    run_sql(f"""
        DELETE FROM {CUSTOMERS}
        WHERE total_spent < 50
    """)
    snap_delete_id = current_snapshot()
    return rows_before_delete, snap_delete_id


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 7 — Verify the delete
    """)
    return


@app.cell
def _(CUSTOMERS, query, snap_delete_id):
    snap_delete_id  # run after the DELETE
    rows_after_delete = int(query(f"SELECT COUNT(*) AS remaining_customers FROM {CUSTOMERS}").iloc[0, 0])
    _df_after_delete = query(f"""
        SELECT customer_id, name, total_spent
        FROM {CUSTOMERS}
        ORDER BY customer_id
    """)
    return (rows_after_delete,)


@app.cell(hide_code=True)
def _(before_after, mo, rows_after_delete, rows_before_delete, snap_bonus_id, snap_delete_id):
    _ok = rows_after_delete == 7
    mo.vstack(
        [
            before_after(snap_bonus_id, snap_delete_id, "Before DELETE", "After DELETE"),
            mo.callout(
                mo.md(
                    f"**{rows_before_delete - rows_after_delete} rows removed, {rows_after_delete} remaining.** "
                    "Carol Davis (C003, $45.00), Frank Brown (C006, $30.00) and Iris Chen (C009, $15.50) are gone."
                ),
                kind="success" if _ok else "warn",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 8 — Time travel to see deleted rows

    The deleted rows still exist in earlier snapshots. Find the snapshot **before** the DELETE, which is the
    last UPDATE, and query the rows that were removed:
    """)
    return


@app.cell
def _(SCHEMA, query, snap_delete_id):
    snap_delete_id  # run after Step 7
    snapshots_c = query(f"""
        SELECT snapshot_id, operation, committed_at
        FROM iceberg.{SCHEMA}."customers$snapshots"
        ORDER BY committed_at
    """)
    # The snapshot before the DELETE is the DELETE snapshot's parent (the loyalty-bonus UPDATE)
    pre_delete_snap_id = int(
        query(f'SELECT parent_id FROM iceberg.{SCHEMA}."customers$snapshots" WHERE snapshot_id = {snap_delete_id}').iloc[0, 0]
    )
    return pre_delete_snap_id, snapshots_c


@app.cell
def _(CUSTOMERS, pre_delete_snap_id, query):
    df_deleted_rows = query(f"""
        SELECT customer_id, name, total_spent
        FROM {CUSTOMERS}
        FOR VERSION AS OF {pre_delete_snap_id}
        WHERE total_spent < 50
        ORDER BY customer_id
    """)
    return (df_deleted_rows,)


@app.cell(hide_code=True)
def _(df_deleted_rows, mo, pre_delete_snap_id, snap_bonus_id, snapshots_c):
    mo.hstack(
        [
            mo.vstack(
                [
                    mo.md(f"**Snapshot history.** The DELETE's parent is `{pre_delete_snap_id}`"
                          + (" (the loyalty-bonus UPDATE)." if pre_delete_snap_id == snap_bonus_id else ".")),
                    mo.ui.table(snapshots_c, selection=None, show_column_summaries=False),
                ]
            ),
            mo.vstack(
                [
                    mo.md(f"**`FOR VERSION AS OF {pre_delete_snap_id}`**"),
                    mo.ui.table(df_deleted_rows, selection=None, show_column_summaries=False),
                    mo.callout(
                        mo.md(f"**{len(df_deleted_rows)} deleted rows recovered.** They are gone from the current table but kept in the snapshot history."),
                        kind="success",
                    ),
                ]
            ),
        ],
        widths="equal",
        align="start",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part D — MERGE INTO (upsert)

    ### Step 9 — Create a staging table

    The staging table mixes existing customers (with updated data) and brand-new customers:

    - **C001, C002, C010**: existing customers with higher spend (should be **updated**)
    - **C011, C012**: new customers (should be **inserted**)
    """)
    return


@app.cell
def _(STAGING, pre_delete_snap_id, run_sql):
    pre_delete_snap_id  # run after Part C (Step 1 already dropped any old staging table)
    run_sql(f"""
        CREATE TABLE {STAGING} (
          customer_id VARCHAR,
          name VARCHAR,
          email VARCHAR,
          tier VARCHAR,
          total_spent DECIMAL(10,2),
          signup_date DATE
        )
    """)
    run_sql(f"""
        INSERT INTO {STAGING} VALUES
          ('C001', 'Alice Johnson',   'alice.johnson@example.com',   'gold',  1200.00, DATE '2024-01-15'),
          ('C002', 'Bob Smith',       'bob.smith@example.com',       'gold',   600.00, DATE '2024-02-20'),
          ('C010', 'Jack Anderson',   'jack.anderson@example.com',   'gold',   800.00, DATE '2024-10-01'),
          ('C011', 'Karen White',     'karen.white@example.com',     'silver', 350.00, DATE '2025-01-10'),
          ('C012', 'Leo Garcia',      'leo.garcia@example.com',      'bronze', 120.00, DATE '2025-02-15')
    """)
    staging_loaded = True
    return (staging_loaded,)


@app.cell(hide_code=True)
def _(STAGING, mo, query, staging_loaded):
    staging_loaded  # run after the staging insert
    mo.vstack(
        [
            mo.md(f"**Staging data:** `{STAGING}` (3 existing + 2 new customers)"),
            mo.ui.table(query(f"SELECT * FROM {STAGING} ORDER BY customer_id"), selection=None, show_column_summaries=False),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 10 — MERGE INTO

    Match on `customer_id`:

    - **WHEN MATCHED** and staging shows higher spend: UPDATE the target
    - **WHEN NOT MATCHED**: INSERT the new row
    """)
    return


@app.cell
def _(CUSTOMERS, STAGING, current_snapshot, run_sql, staging_loaded):
    staging_loaded  # run after Step 9
    pre_merge_snap_id = current_snapshot()  # capture the pre-merge snapshot for comparison
    run_sql(f"""
        MERGE INTO {CUSTOMERS} AS target
        USING {STAGING} AS staging
        ON target.customer_id = staging.customer_id
        WHEN MATCHED AND staging.total_spent > target.total_spent THEN
          UPDATE SET
            email = staging.email,
            tier = staging.tier,
            total_spent = staging.total_spent
        WHEN NOT MATCHED THEN
          INSERT (customer_id, name, email, tier, total_spent, signup_date)
          VALUES (staging.customer_id, staging.name, staging.email,
                  staging.tier, staging.total_spent, staging.signup_date)
    """)
    snap_merge_id = current_snapshot()
    return pre_merge_snap_id, snap_merge_id


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 11 — Verify the MERGE results

    Expected: **C001** (Alice) → $1200.00, **C002** (Bob) → $600.00, **C010** (Jack) → $800.00,
    **C011** (Karen) and **C012** (Leo) newly inserted, every other customer unchanged.
    """)
    return


@app.cell
def _(CUSTOMERS, query, snap_merge_id):
    snap_merge_id  # run after the MERGE
    df_after_merge = query(f"""
        SELECT customer_id, name, tier, total_spent
        FROM {CUSTOMERS}
        ORDER BY customer_id
    """)
    return (df_after_merge,)


@app.cell(hide_code=True)
def _(before_after, df_after_merge, mo, pre_merge_snap_id, snap_merge_id):
    mo.vstack(
        [
            before_after(pre_merge_snap_id, snap_merge_id, "Before MERGE", "After MERGE"),
            mo.callout(
                mo.md(f"**{len(df_after_merge)} customers after the MERGE.** One atomic statement updated 3 rows and inserted 2."),
                kind="success" if len(df_after_merge) == 9 else "warn",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 12 — Full snapshot history

    Every operation has been tracked, from the initial INSERT through the UPDATEs, the DELETE and the MERGE:
    """)
    return


@app.cell
def _(SCHEMA, query, snap_merge_id):
    snap_merge_id  # run after Step 11
    snapshots_final = query(f"""
        SELECT
          snapshot_id,
          parent_id,
          operation,
          committed_at
        FROM iceberg.{SCHEMA}."customers$snapshots"
        ORDER BY committed_at
    """)
    return (snapshots_final,)


@app.cell(hide_code=True)
def _(mo, snap1_id, snap_bonus_id, snap_delete_id, snap_merge_id, snap_promote_id, snapshots_final):
    step_labels = {
        snap1_id: "Initial 10-row insert",
        snap_promote_id: "UPDATE: promote to gold",
        snap_bonus_id: "UPDATE: loyalty bonus",
        snap_delete_id: "DELETE: low activity",
        snap_merge_id: "MERGE: updated 3 + inserted 2",
    }
    _view = snapshots_final.assign(
        what_happened=snapshots_final["snapshot_id"].map(lambda s: step_labels.get(int(s), "CREATE TABLE (empty)"))
    )
    mo.vstack(
        [
            mo.mermaid(
                "gitGraph\n"
                + "\n".join(f'    commit id: "{r.operation}: {r.what_happened[:28]}"' for r in _view.itertuples())
            ),
            mo.ui.table(_view, selection=None, show_column_summaries=False),
        ]
    )
    return (step_labels,)


@app.cell(hide_code=True)
def _(mo, step_labels):
    mo.md("""
    ### Try it: browse any snapshot

    Pick a snapshot to see the table exactly as it was after that operation.
    """)
    snapshot_picker = mo.ui.dropdown(
        {f"{label} ({sid})": sid for sid, label in step_labels.items()},
        value=next(f"{label} ({sid})" for sid, label in step_labels.items() if label.startswith("DELETE")),
        label="Snapshot",
    )
    snapshot_picker
    return (snapshot_picker,)


@app.cell(hide_code=True)
def _(customers_at, mo, snapshot_picker):
    _df = customers_at(snapshot_picker.value)
    mo.vstack(
        [
            mo.md(f"```sql\nSELECT * FROM iceberg.shop.customers FOR VERSION AS OF {snapshot_picker.value}\n```"),
            mo.hstack(
                [
                    mo.stat(len(_df), label="Rows", bordered=True),
                    mo.stat(f"${_df['total_spent'].astype(float).sum():,.2f}", label="Total spent", bordered=True),
                    mo.stat(int((_df["tier"] == "gold").sum()), label="Gold customers", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.table(_df, selection=None, show_column_summaries=False),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part E — Combining with time travel

    ### Step 13 — Compare the current state with the original state

    A time-travel `FULL OUTER JOIN` builds a full diff: which customers were ADDED, MODIFIED or DELETED since the
    original insert (`snap1_id`).
    """)
    return


@app.cell
def _(CUSTOMERS, query, snap1_id, snapshots_final):
    snapshots_final  # run after all mutations
    df_diff = query(f"""
        SELECT
          COALESCE(c.customer_id, h.customer_id) AS customer_id,
          h.name AS original_name,
          h.tier AS original_tier,
          h.total_spent AS original_spent,
          c.name AS current_name,
          c.tier AS current_tier,
          c.total_spent AS current_spent,
          CASE
            WHEN c.customer_id IS NULL THEN 'DELETED'
            WHEN h.customer_id IS NULL THEN 'ADDED'
            WHEN c.total_spent <> h.total_spent OR c.tier <> h.tier THEN 'MODIFIED'
            ELSE 'UNCHANGED'
          END AS status
        FROM {CUSTOMERS} c
        FULL OUTER JOIN {CUSTOMERS} FOR VERSION AS OF {snap1_id} h
          ON c.customer_id = h.customer_id
        ORDER BY COALESCE(c.customer_id, h.customer_id)
    """)
    return (df_diff,)


@app.cell(hide_code=True)
def _(df_diff, mo):
    _n = df_diff["status"].value_counts()
    mo.vstack(
        [
            mo.hstack(
                [mo.stat(int(_n.get(s, 0)), label=s, bordered=True) for s in ("ADDED", "MODIFIED", "DELETED", "UNCHANGED")],
                widths="equal",
            ),
            mo.ui.table(df_diff, selection=None, show_column_summaries=False, page_size=12),
            mo.callout(
                mo.md(
                    "Expected: C001, C002, C004, C005, C008 and C010 **MODIFIED**; C003, C006 and C009 **DELETED**; "
                    "C007 **UNCHANGED**; C011 and C012 **ADDED**."
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
    ## Wrap-up
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.accordion(
        {
            "Key takeaways": mo.md(
                """
                1. Iceberg supports UPDATE, DELETE and MERGE INTO, not just INSERT and partition overwrite
                2. Every mutation is one atomic commit, which means one immutable snapshot (`overwrite` or `delete`)
                3. `FOR VERSION AS OF <snapshot_id>` reads any earlier state, including rows you deleted
                4. MERGE INTO is the upsert pattern for incremental loads: update matched rows, insert new ones
                5. Record snapshot IDs as you go. Trino's `CREATE TABLE` adds an empty first snapshot, so position-based lookups go wrong
                """
            ),
            "Exercises": mo.md(
                """
                1. **Lowercase all emails:** run an UPDATE that sets all email addresses to lowercase with `LOWER(email)`.
                   Then use time travel to check that the old mixed-case emails are still in the previous snapshot.
                2. **DELETE and rollback:** DELETE all bronze-tier customers. Then use `CALL iceberg.system.rollback_to_snapshot`
                   to undo the delete. Verify the bronze customers are back.
                   *(On this stack's Trino the `CALL` form is denied by access control and deprecated; use
                   `ALTER TABLE iceberg.shop.customers EXECUTE rollback_to_snapshot(<snapshot_id>)` instead.)*
                3. **Three-way MERGE:** create a new staging table and write a MERGE with three conditions:
                   - `WHEN MATCHED AND staging.total_spent > target.total_spent THEN UPDATE`
                   - `WHEN MATCHED AND staging.total_spent < target.total_spent THEN DELETE`
                   - `WHEN NOT MATCHED THEN INSERT`

                   Verify that all three actions occurred.
                4. **Inspect snapshot metadata:** query `iceberg.shop."customers$snapshots"` and examine every row. How many
                   snapshots exist? What operation type does each show? Look at the `summary` column: what extra details
                   does Iceberg record for each operation?
                5. **Challenge: incremental load pipeline.** Write a complete incremental load sequence:
                   - Create a new staging table with fresh data (some overlapping, some new customer IDs)
                   - MERGE it into the customers table
                   - Query the snapshot history to work out how many rows were inserted vs updated
                   - Compare the before-MERGE and after-MERGE snapshots with a time-travel JOIN to produce a detailed changelog

                   *Hint:* the `summary` field in `"customers$snapshots"` has keys like `added-records` and
                   `changed-partition-count` that tell you exactly what happened.
                """
            ),
            "Next lab": mo.md(
                "**Lab 15 — Branching & Tagging:** give snapshots names. Use tags for audits and branches for safe experiments."
            ),
        },
        multiple=True,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    **Congratulations!** You can now perform row-level mutations (UPDATE, DELETE, MERGE INTO) on Iceberg tables,
    with every change tracked as an immutable snapshot. That gives you full audit trails, time travel and rollback
    through Polaris.
    """)
    return


if __name__ == "__main__":
    app.run()
