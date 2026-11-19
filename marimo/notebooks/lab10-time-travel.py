import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 10 — Time Travel")


@app.cell(hide_code=True)
def _():
    import os
    from datetime import timezone

    import marimo as mo
    import pandas as pd
    import requests
    import urllib3
    from sqlalchemy import create_engine, text

    urllib3.disable_warnings()

    TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
    POLARIS_HOST = os.environ.get("POLARIS_HOST", "localhost")
    POLARIS = f"http://{POLARIS_HOST}:8181"
    POLARIS_HEALTH = f"http://{POLARIS_HOST}:8182/q/health"
    TRINO_INFO = f"https://{TRINO_HOST}:8443/v1/info"
    CATALOG_NAME = "polaris_warehouse"
    REALM = "POLARIS"

    trino = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return CATALOG_NAME, POLARIS, POLARIS_HEALTH, REALM, TRINO_INFO, mo, pd, requests, text, timezone, trino


@app.cell(hide_code=True)
def _(CATALOG_NAME, POLARIS, REALM, requests):
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

    return (drop_own_table,)


@app.cell(hide_code=True)
def _(mo, pd, text, timezone, trino):
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
            values = [v for v in df[col] if v is not None]
            # Snapshot IDs are 64-bit; keep them exact by showing them as text.
            if values and all(isinstance(v, int) and not isinstance(v, bool) for v in values) and any(
                abs(v) > 2**53 for v in values
            ):
                df[col] = df[col].map(lambda v: "" if v is None else str(v))
        return df.convert_dtypes()

    def grid(df, **kwargs):
        return mo.ui.table(df, selection=None, show_column_summaries=False, **kwargs)

    def utc_literal(ts):
        """Format a timestamp as a Trino TIMESTAMP literal in UTC."""
        return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f UTC")

    def snapshot_frame():
        df = sql(
            """
            SELECT snapshot_id, parent_id, operation, committed_at, summary
            FROM iceberg.shop."inventory$snapshots"
            ORDER BY committed_at
            """
        )
        df["total_records"] = [int(s.get("total-records", 0)) for s in df["summary"]]
        df["added_records"] = [int(s.get("added-records", 0)) for s in df["summary"]]
        df["deleted_records"] = [int(s.get("deleted-records", 0)) for s in df["summary"]]
        return df.drop(columns=["summary"])

    return grid, snapshot_frame, sql, utc_literal


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar(
        [
            mo.md("### Lab 10\n**Time Travel**"),
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
                # Lab 10 — Time Travel

                **Level:** 5 (Advanced) &nbsp;|&nbsp; **Time:** 25 minutes

                **Goal:** Query historical table states, compare versions, and roll back to previous snapshots
                using Iceberg's time travel capabilities.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Build an `iceberg.shop.inventory` table with a history of INSERT, UPDATE and DELETE snapshots
                    2. Read past states with `FOR TIMESTAMP AS OF` and `FOR VERSION AS OF`
                    3. Diff the current table against an old version
                    4. Roll back to the snapshot before the delete, and see that history is kept
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
            mo.stat("iceberg.shop", label="Namespace", caption="table: inventory", bordered=True),
        ],
        widths="equal",
    )
    return (stack_ok,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Concepts

    Every write in Iceberg creates an **immutable snapshot**, a complete picture of the table at that moment.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "Snapshots": mo.md(
                """
                Every INSERT, UPDATE or DELETE commits a new snapshot. Each snapshot points to the data files
                that make up the table at that moment, plus its **parent** snapshot.

                **Use case:** a full audit trail of every change.
                """
            ),
            "Time travel": mo.md(
                """
                Query any past state by **timestamp** (`FOR TIMESTAMP AS OF`) or **snapshot ID** (`FOR VERSION AS OF`).
                Iceberg just reads the data files the old snapshot points to.

                **Use case:** reproduce past results, debug pipelines.
                """
            ),
            "Rollback": mo.md(
                """
                Move the table's current pointer back to a previous snapshot. No data is copied,
                and the later snapshots stay in the history.

                **Use case:** recover from bad writes or accidental deletes.
                """
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.mermaid(
                """
                flowchart LR
                    C["CREATE TABLE<br/>empty snapshot"] --> S1["Snapshot 1<br/>INSERT<br/>5 rows"]
                    S1 --> S2["Snapshot 2<br/>UPDATE quantity<br/>5 rows"]
                    S2 --> S3["Snapshot 3<br/>DELETE product<br/>4 rows"]
                    S3 -. "rollback_to_snapshot<br/>restores this state" .-> S2
                    Q(["FOR TIMESTAMP AS OF '...'<br/>FOR VERSION AS OF id"]) -. "query any past state" .-> S1
                """
            ),
            mo.callout(
                mo.md(
                    "**Polaris stores the metadata for every snapshot.** You can time-travel from any engine "
                    "(Trino, Spark, PyIceberg) and always see the same, consistent history."
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
    ## Part A — Build a snapshot history

    ### Step 1 — Create the inventory table

    The notebook runs the SQL for you. To follow along in the Trino CLI instead:

    ```bash
    podman exec -e TRINO_PASSWORD=admin123 -it trino \
      trino --server https://localhost:8443 --user admin --password --insecure
    # or: docker exec ... (same arguments)
    ```

    This lab owns `iceberg.shop.inventory`: it drops and recreates the table so every run starts
    with a clean, reproducible history.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            "**Why not `DROP TABLE` in Trino?** Trino always asks Polaris to *purge* the files, and this "
            "Polaris catalog has `DROP_WITH_PURGE_ENABLED` turned off, so the drop fails with *Failed to drop table*. "
            "The notebook removes the old table through the Iceberg REST API instead "
            "(`DELETE …/namespaces/shop/tables/inventory`, no purge). The old data files stay in S3, "
            "and the new table gets a fresh location."
        ),
        kind="neutral",
    )
    return


@app.cell
def _(drop_own_table, mo, sql, stack_ok):
    assert stack_ok
    sql("CREATE SCHEMA IF NOT EXISTS iceberg.shop")
    _dropped = drop_own_table("shop", "inventory")  # instead of DROP TABLE IF EXISTS iceberg.shop.inventory
    sql(
        """
        CREATE TABLE iceberg.shop.inventory (
          product_id VARCHAR,
          product_name VARCHAR,
          quantity INT,
          last_updated TIMESTAMP(6) WITH TIME ZONE
        )
        """
    )
    inventory_created = True
    mo.callout(
        mo.md(
            "Table `iceberg.shop.inventory` "
            + ("dropped and recreated." if _dropped else "created.")
        ),
        kind="success",
    )
    return (inventory_created,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 2 — Insert the initial inventory (Snapshot 1)

    Five products with their starting quantities:
    """)
    return


@app.cell
def _(inventory_created, sql):
    assert inventory_created
    sql(
        """
        INSERT INTO iceberg.shop.inventory VALUES
          ('P001', 'Wireless Mouse',      150, CURRENT_TIMESTAMP),
          ('P002', 'Mechanical Keyboard',  75, CURRENT_TIMESTAMP),
          ('P003', 'USB-C Hub',           200, CURRENT_TIMESTAMP),
          ('P004', 'Monitor Stand',        50, CURRENT_TIMESTAMP),
          ('P005', 'Webcam HD',           120, CURRENT_TIMESTAMP)
        """
    )
    initial_rows = sql("SELECT * FROM iceberg.shop.inventory ORDER BY product_id")
    return (initial_rows,)


@app.cell(hide_code=True)
def _(grid, initial_rows):
    grid(initial_rows)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 3 — View the snapshot history

    The `"inventory$snapshots"` metadata table lists every snapshot. Note each `snapshot_id` and
    `committed_at`: they are what you time-travel with.
    """)
    return


@app.cell
def _(initial_rows, sql):
    assert len(initial_rows) == 5
    snapshots_1 = sql(
        """
        SELECT snapshot_id, parent_id, operation, committed_at
        FROM iceberg.shop."inventory$snapshots"
        ORDER BY committed_at
        """
    )
    return (snapshots_1,)


@app.cell(hide_code=True)
def _(grid, mo, snapshots_1):
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(snapshots_1), label="Snapshots", bordered=True),
                    mo.stat(snapshots_1.iloc[-1]["operation"], label="Latest operation", bordered=True),
                    mo.stat(
                        snapshots_1.iloc[-1]["committed_at"].strftime("%H:%M:%S"),
                        label="Committed at",
                        caption="latest snapshot",
                        bordered=True,
                    ),
                ],
                widths="equal",
            ),
            grid(snapshots_1),
            mo.callout(
                mo.md(
                    f"You see **{len(snapshots_1)} snapshots**, not 1. Recent Trino versions commit an "
                    "**empty snapshot when `CREATE TABLE` runs**; the INSERT adds the second one. "
                    "This notebook calls the INSERT *Snapshot 1*, as in the diagram above."
                ),
                kind="neutral",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 4 — Update quantities: simulate a restock (Snapshot 2)

    Add 100 units to product P001:
    """)
    return


@app.cell
def _(snapshots_1, sql):
    assert len(snapshots_1) >= 1
    sql(
        """
        UPDATE iceberg.shop.inventory
        SET quantity = quantity + 100,
            last_updated = CURRENT_TIMESTAMP
        WHERE product_id = 'P001'
        """
    )
    restocked = True
    return (restocked,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 5 — Delete a product: discontinue an item (Snapshot 3)

    Remove product P005 (Webcam HD):
    """)
    return


@app.cell
def _(restocked, sql):
    assert restocked
    sql(
        """
        DELETE FROM iceberg.shop.inventory
        WHERE product_id = 'P005'
        """
    )
    discontinued = True
    return (discontinued,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 6 — View all 3 snapshots

    Same query as Step 3, now with the `summary` map. Below, the summary is unpacked into record counts.
    """)
    return


@app.cell
def _(discontinued, sql):
    assert discontinued
    snapshots_all_raw = sql(
        """
        SELECT
          snapshot_id,
          parent_id,
          operation,
          committed_at,
          summary
        FROM iceberg.shop."inventory$snapshots"
        ORDER BY committed_at
        """
    )
    return (snapshots_all_raw,)


@app.cell(hide_code=True)
def _(snapshot_frame, snapshots_all_raw, utc_literal):
    assert len(snapshots_all_raw) >= 3
    snapshots_all = snapshot_frame()

    # Skip the empty snapshot that CREATE TABLE commits; the next three are INSERT, UPDATE and DELETE.
    _is_create = (snapshots_all["parent_id"] == "") & (snapshots_all["total_records"] == 0)
    _writes = snapshots_all[~_is_create].reset_index(drop=True)
    assert len(_writes) == 3, f"expected 3 write snapshots, found {len(_writes)}"

    snap1_id = int(_writes.loc[0, "snapshot_id"])
    snap2_id = int(_writes.loc[1, "snapshot_id"])
    snap3_id = int(_writes.loc[2, "snapshot_id"])
    snap1_ts = utc_literal(_writes.loc[0, "committed_at"])

    snapshot_labels = {
        "CREATE TABLE (empty)": int(snapshots_all.loc[_is_create].iloc[0]["snapshot_id"]) if _is_create.any() else None,
        "Snapshot 1 — INSERT 5 products": snap1_id,
        "Snapshot 2 — UPDATE (restock P001)": snap2_id,
        "Snapshot 3 — DELETE P005": snap3_id,
    }
    snapshot_labels = {k: v for k, v in snapshot_labels.items() if v is not None}
    _names = {str(v): k for k, v in snapshot_labels.items()}
    snapshots_all.insert(0, "lab_name", [_names.get(s, "") for s in snapshots_all["snapshot_id"]])
    return snap1_id, snap1_ts, snap2_id, snap3_id, snapshot_labels, snapshots_all


@app.cell(hide_code=True)
def _(grid, mo, snapshots_all):
    mo.vstack(
        [
            grid(snapshots_all),
            mo.md(
                """
                | # | Operation | What happened |
                |---|-----------|---------------|
                | 1 | `append` | Initial 5-row insert |
                | 2 | `overwrite` | Updated P001 quantity (copy-on-write rewrites the file) |
                | 3 | `delete` | Removed P005 |
                """
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo, snap1_id, snap1_ts, snap2_id, snap3_id):
    mo.hstack(
        [
            mo.stat(str(snap1_id), label="snap1_id", caption="initial insert", bordered=True),
            mo.stat(str(snap2_id), label="snap2_id", caption="update / restock", bordered=True),
            mo.stat(str(snap3_id), label="snap3_id", caption="delete", bordered=True),
            mo.stat(snap1_ts[11:23], label="snap1_ts", caption="UTC, used in Step 7", bordered=True),
        ],
        widths="equal",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part B — Time travel queries

    ### Step 7 — Query the original state by timestamp

    `FOR TIMESTAMP AS OF` reads the table as it was right after the initial insert.
    The notebook fills in Snapshot 1's `committed_at` (in UTC) for you.

    **How it works:** Iceberg finds the latest snapshot whose `committed_at` is at or before the given
    timestamp, then reads the data files of that snapshot.
    """)
    return


@app.cell
def _(snap1_ts, sql):
    df_ts = sql(
        f"""
        SELECT *
        FROM iceberg.shop.inventory
        FOR TIMESTAMP AS OF TIMESTAMP '{snap1_ts}'
        ORDER BY product_id
        """
    )
    return (df_ts,)


@app.cell(hide_code=True)
def _(df_ts, grid, mo, snap1_ts):
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"Table state at `{snap1_ts}`: **{len(df_ts)} rows**. "
                    "All 5 products with their original quantities (P001 has 150, P005 exists)."
                ),
                kind="success" if len(df_ts) == 5 else "warn",
            ),
            grid(df_ts),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 8 — Query by snapshot ID

    `FOR VERSION AS OF` takes the exact snapshot ID. Version-based travel is precise:
    it always returns the snapshot you asked for.
    """)
    return


@app.cell
def _(snap1_id, sql):
    df_ver = sql(
        f"""
        SELECT *
        FROM iceberg.shop.inventory
        FOR VERSION AS OF {snap1_id}
        ORDER BY product_id
        """
    )
    return (df_ver,)


@app.cell(hide_code=True)
def _(df_ts, df_ver, grid, mo, snap1_id):
    _same = df_ver.drop(columns=["last_updated"]).equals(df_ts.drop(columns=["last_updated"]))
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"Snapshot `{snap1_id}`: **{len(df_ver)} rows**, "
                    + ("the same result as the timestamp query." if _same else "**different** from the timestamp query.")
                ),
                kind="success" if _same else "warn",
            ),
            grid(df_ver),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Try it: travel to any snapshot

    Pick a snapshot. The query below runs `FOR VERSION AS OF <id>` with the ID you picked.
    """)
    return


@app.cell(hide_code=True)
def _(mo, snapshot_labels):
    snapshot_picker = mo.ui.dropdown(
        snapshot_labels,
        value="Snapshot 2 — UPDATE (restock P001)",
        label="Snapshot",
    )
    snapshot_picker
    return (snapshot_picker,)


@app.cell(hide_code=True)
def _(grid, mo, snapshot_picker, sql):
    _sid = snapshot_picker.value
    _query = f"SELECT * FROM iceberg.shop.inventory FOR VERSION AS OF {_sid} ORDER BY product_id"
    _df = sql(_query)
    _p001 = _df.loc[_df["product_id"] == "P001", "quantity"]
    mo.vstack(
        [
            mo.md(f"```sql\n{_query}\n```"),
            mo.hstack(
                [
                    mo.stat(len(_df), label="Rows", bordered=True),
                    mo.stat(int(_p001.iloc[0]) if len(_p001) else "—", label="P001 quantity", bordered=True),
                    mo.stat("yes" if (_df["product_id"] == "P005").any() else "no", label="P005 present", bordered=True),
                ],
                widths="equal",
            ),
            grid(_df) if len(_df) else mo.callout("The table was empty at this snapshot.", kind="neutral"),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 9 — Compare the current and historical state

    This is where time travel becomes truly useful. Join the current table against Snapshot 1
    to see exactly what changed:
    """)
    return


@app.cell
def _(snap1_id, sql):
    df_diff = sql(
        f"""
        SELECT
          COALESCE(c.product_id, h.product_id) AS product_id,
          h.product_name AS original_name,
          h.quantity AS original_qty,
          c.quantity AS current_qty,
          c.quantity - h.quantity AS qty_change,
          CASE
            WHEN c.product_id IS NULL THEN 'DELETED'
            WHEN h.product_id IS NULL THEN 'ADDED'
            WHEN c.quantity <> h.quantity THEN 'MODIFIED'
            ELSE 'UNCHANGED'
          END AS status
        FROM iceberg.shop.inventory c
        FULL OUTER JOIN iceberg.shop.inventory FOR VERSION AS OF {snap1_id} h
          ON c.product_id = h.product_id
        ORDER BY COALESCE(c.product_id, h.product_id)
        """
    )
    return (df_diff,)


@app.cell(hide_code=True)
def _(df_diff, grid, mo):
    _colors = {"DELETED": "#fde2e1", "MODIFIED": "#fff4d6", "ADDED": "#e3f6e5"}

    def _style(row_id, column, value):
        status = df_diff.loc[int(row_id), "status"]
        return {"backgroundColor": _colors[status]} if status in _colors else {}

    _counts = df_diff["status"].value_counts()
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(int(_counts.get(s, 0)), label=s.title(), bordered=True)
                    for s in ("MODIFIED", "DELETED", "ADDED", "UNCHANGED")
                ],
                widths="equal",
            ),
            grid(df_diff, style_cell=_style),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part C — Rollback

    ### Step 10 — Roll back to before the delete

    Revert the table to **Snapshot 2** (after the restock, before the delete). Product P005 will reappear.
    Rollback changes the live table, so it waits for you to click the button.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            """
            **Two spellings of the same procedure.** Older guides use

            ```sql
            CALL iceberg.system.rollback_to_snapshot('shop', 'inventory', <snapshot_2_id>);
            ```

            Current Trino versions replace it with the table procedure `ALTER TABLE ... EXECUTE rollback_to_snapshot(<id>)`,
            and this lab's Trino access rules deny `CALL` on `system` procedures. The notebook uses the `ALTER TABLE` form.
            """
        ),
        kind="info",
    )
    return


@app.cell(hide_code=True)
def _(mo, snap2_id):
    rollback_btn = mo.ui.run_button(label=f"Roll back to Snapshot 2 ({snap2_id})", kind="warn")
    rollback_btn
    return (rollback_btn,)


@app.cell
def _(mo, rollback_btn, snap2_id, sql):
    mo.stop(
        not rollback_btn.value,
        mo.callout(mo.md("Click **Roll back to Snapshot 2** to run the rollback."), kind="neutral"),
    )
    sql(f"ALTER TABLE iceberg.shop.inventory EXECUTE rollback_to_snapshot({snap2_id})")
    mo.callout(mo.md(f"Rolled back `iceberg.shop.inventory` to snapshot `{snap2_id}`."), kind="success")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 11 — Verify the rollback

    Read the current table and the snapshot history again. This step refreshes when you click the button above.
    """)
    return


@app.cell
def _(rollback_btn, sql):
    _clicked = rollback_btn.value  # re-run this cell after a rollback
    df_after_rollback = sql("SELECT * FROM iceberg.shop.inventory ORDER BY product_id")
    snapshots_final = sql(
        """
        SELECT snapshot_id, parent_id, operation, committed_at
        FROM iceberg.shop."inventory$snapshots"
        ORDER BY committed_at
        """
    )
    current_snapshot = sql(
        """SELECT snapshot_id FROM iceberg.shop."inventory$refs" WHERE name = 'main'"""
    ).iloc[0, 0]
    return current_snapshot, df_after_rollback, snapshots_final


@app.cell(hide_code=True)
def _(current_snapshot, df_after_rollback, grid, mo, snap2_id, snap3_id):
    _p005_back = (df_after_rollback["product_id"] == "P005").any()
    if str(current_snapshot) == str(snap2_id) and _p005_back:
        _status = mo.callout(
            mo.md(
                f"**P005 (Webcam HD) is back!** The table is at Snapshot 2 again: "
                f"{len(df_after_rollback)} rows, P001 still has the restocked quantity."
            ),
            kind="success",
        )
    elif str(current_snapshot) == str(snap3_id):
        _status = mo.callout(
            mo.md(
                f"**No rollback yet.** The table is still at Snapshot 3 ({len(df_after_rollback)} rows, P005 deleted). "
                "Click the button in Step 10, and this step updates."
            ),
            kind="neutral",
        )
    else:
        _status = mo.callout(
            mo.md(f"The table's current snapshot is `{current_snapshot}`. P005 present: {_p005_back}."),
            kind="warn",
        )
    mo.vstack([_status, grid(df_after_rollback)])
    return


@app.cell(hide_code=True)
def _(current_snapshot, grid, mo, snapshot_labels, snapshots_final):
    _names = {str(v): k for k, v in snapshot_labels.items()}
    _history = snapshots_final.copy()
    _history.insert(0, "lab_name", [_names.get(s, "") for s in _history["snapshot_id"]])
    _history["current"] = ["◀ current" if s == str(current_snapshot) else "" for s in _history["snapshot_id"]]
    mo.vstack(
        [
            mo.md(f"**Snapshot history ({len(_history)} snapshots)**"),
            grid(_history),
            mo.callout(
                mo.md(
                    "**Rollback does not erase history.** All the original snapshots remain; "
                    "the table's current pointer simply moves back to Snapshot 2."
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 12 — Use cases

    | Use case | How time travel helps |
    |----------|-----------------------|
    | Auditing & compliance | Query the exact table state at any point in time |
    | Recovering from bad writes | Roll back to the last known good snapshot |
    | Debugging data pipelines | Compare before/after to find what changed |
    | Reproducible analytics | Re-run a report as of a specific date |
    | Regulatory reporting | Prove what data looked like on a given date |
    | A/B testing data changes | Compare two versions side by side |
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
                1. Every INSERT, UPDATE and DELETE commits an immutable snapshot; `"table$snapshots"` lists them
                2. `FOR TIMESTAMP AS OF` picks the latest snapshot at or before a time; `FOR VERSION AS OF` picks an exact ID
                3. A `FULL OUTER JOIN` between the current table and a past version shows exactly what changed
                4. `ALTER TABLE ... EXECUTE rollback_to_snapshot(id)` moves the current pointer; history is kept
                5. Polaris holds the metadata, so every engine sees the same history
                """
            ),
            "Exercises": mo.md(
                """
                1. **Add more mutations:** insert 3 new products, update 2 existing ones, then delete 1.
                   Use `"inventory$snapshots"` to verify that 3 new snapshots were created.
                2. **Time travel to every snapshot:** write a query for each snapshot in the history.
                   Confirm the row count matches expectations at each point.
                3. **Compare any two snapshots:** adapt the Step 9 comparison query to compare Snapshot 1 vs Snapshot 3
                   (skipping Snapshot 2). What does the diff look like?
                4. **Rollback chain:** roll back to the original Snapshot 1 (before any updates). Verify all 5 products
                   have their original quantities. Then think about it: can you "undo" a rollback?
                5. **Challenge: build a changelog query.** Write a single SQL query that shows what changed between two
                   specific snapshots. For each row, show the `product_id`, the old values, the new values, and a status
                   column (`ADDED`, `DELETED`, `MODIFIED`, `UNCHANGED`). Test it across multiple snapshot pairs.

                   *Hint:* use `FULL OUTER JOIN` between `FOR VERSION AS OF <old_id>` and `FOR VERSION AS OF <new_id>`,
                   similar to Step 9 but with two versioned references instead of one.
                """
            ),
            "Next lab": mo.md(
                """
                **Lab 11 — Hidden Partitioning & Partition Evolution:** let Iceberg prune files from plain `WHERE`
                clauses, and change the partition layout without rewriting data.

                **Congratulations!** You can now query any historical state, compare versions, and recover from
                mistakes, all powered by Iceberg's immutable snapshots and Polaris as the central catalog.
                """
            ),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
