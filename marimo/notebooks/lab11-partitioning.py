import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 11 — Hidden Partitioning")


@app.cell(hide_code=True)
def _():
    import os
    import re
    from datetime import datetime, timedelta, timezone

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
    return (
        CATALOG_NAME,
        POLARIS,
        POLARIS_HEALTH,
        REALM,
        TRINO_INFO,
        datetime,
        mo,
        pd,
        re,
        requests,
        text,
        timedelta,
        timezone,
        trino,
    )


@app.cell(hide_code=True)
def _(CATALOG_NAME, POLARIS, REALM, datetime, mo, pd, re, requests, text, timedelta, timezone, trino):
    def sql(statement):
        """Run one Trino statement and return the result as a DataFrame (empty for DDL)."""
        with trino.connect() as conn:
            result = conn.execute(text(statement))
            if not result.returns_rows:
                return pd.DataFrame()
            columns = list(result.keys())
            rows = [tuple(r) for r in result.fetchall()]
        return pd.DataFrame(rows, columns=columns, dtype=object).infer_objects()

    def grid(df, **kwargs):
        return mo.ui.table(df, selection=None, show_column_summaries=False, **kwargs)

    def insert_events(table, events):
        """One INSERT per event, so each event lands in its own data file."""
        with trino.connect() as conn:
            for eid, uid, etype, page, etime, country in events:
                conn.execute(
                    text(
                        f"INSERT INTO {table} VALUES "
                        f"('{eid}', '{uid}', '{etype}', '{page}', "
                        f"TIMESTAMP '{etime}', '{country}')"
                    )
                )

    _EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def _readable(name, value):
        # Iceberg stores hour() and month() partitions as counts since 1970; show them as dates.
        if value is None:
            return None
        if name.endswith("_hour"):
            return (_EPOCH + timedelta(hours=int(value))).strftime("%Y-%m-%d-%H")
        if name.endswith("_month"):
            return f"{1970 + int(value) // 12}-{int(value) % 12 + 1:02d}"
        return str(value)

    def flatten_partitions(df):
        """Split the `partition` row column of a $partitions / $files table into one column per field."""
        fields = [dict(zip(p._names, p)) for p in df["partition"]]
        names = []
        for f in fields:
            names += [n for n in f if n not in names]
        flat = pd.DataFrame([{n: _readable(n, f.get(n)) for n in names} for f in fields])
        rest = df.drop(columns=["partition"] + [c for c in ("data",) if c in df.columns]).reset_index(drop=True)
        return pd.concat([flat, rest], axis=1)

    def scan_metrics(query):
        """EXPLAIN ANALYZE a query and pull out the table-scan numbers."""
        plan = sql(f"EXPLAIN ANALYZE {query}").iloc[0, 0]
        scan = next((ln.strip() for ln in plan.splitlines() if "Splits:" in ln), "")
        splits = re.search(r"Splits: (\d+)", scan)
        rows = re.search(r"Input: (\d+) rows?", scan)
        physical = re.search(r"Physical input: ([\d.]+\s?\w+)", scan)
        return {
            "splits": int(splits.group(1)) if splits else None,
            "rows": int(rows.group(1)) if rows else None,
            "physical": physical.group(1) if physical else "?",
            "plan": plan,
        }

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

    return drop_own_table, flatten_partitions, grid, insert_events, scan_metrics, sql


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar(
        [
            mo.md("### Lab 11\n**Hidden Partitioning & Partition Evolution**"),
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
                # Lab 11 — Hidden Partitioning & Partition Evolution

                **Level:** 5 (Advanced) &nbsp;|&nbsp; **Time:** 30 minutes

                **Goal:** Understand Iceberg's hidden partition transforms, demonstrate partition pruning,
                and evolve partition specs without rewriting data.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Create `iceberg.shop.web_events` partitioned by `day(event_time)` and `bucket(user_id, 4)`, and load 30 events
                    2. Inspect the hidden partitions and data files through the `$partitions` and `$files` metadata tables
                    3. Compare query plans with and without a filter to see partition pruning
                    4. Evolve the table from day to hour partitions, without rewriting a single file
                    5. Compare `truncate()` with `bucket()` on a second table, `web_events_truncated`
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
            mo.stat("iceberg.shop", label="Namespace", caption="web_events, web_events_truncated", bordered=True),
        ],
        widths="equal",
    )
    return (stack_ok,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Concepts
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "Hive-style partitioning": mo.md(
                """
                The user manages partition columns explicitly:

                - An explicit `event_date` column in the schema
                - `WHERE event_date = '2026-09-24'` in every query, or the whole table is scanned
                - Manual ETL to populate the partition column
                - The directory layout leaks into SQL
                - Changing the partitioning scheme means **rewriting the entire table**
                """
            ),
            "Iceberg hidden partitioning": mo.md(
                """
                Iceberg applies **transforms** automatically at write time. Queries are partition-unaware:
                users write normal `WHERE` clauses on the real columns, and Iceberg translates them into
                partition filters behind the scenes.

                The partition layout is **metadata only**, so it can change later without rewriting data.
                """
            ),
            "Available transforms": mo.md(
                """
                | Transform (Trino syntax) | Partitions by | Example value |
                |--------------------------|---------------|---------------|
                | `year(ts)` | year | `2026` |
                | `month(ts)` | month | `2026-09` |
                | `day(ts)` | day | `2026-09-23` |
                | `hour(ts)` | hour | `2026-09-23-14` |
                | `bucket(col, N)` | hash into N buckets | `0, 1, …, N-1` |
                | `truncate(col, N)` | first N characters | `"abc"` → `"ab"` if N=2 |
                """
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md("**How hidden partitioning works**"),
            mo.mermaid(
                """
                flowchart TD
                    I["INSERT INTO web_events<br/>event_time = '2026-09-23 10:15', user_id = 'user-42'"]
                    I --> T["Iceberg applies day(event_time)<br/>and bucket(user_id, 4)"]
                    T --> D1["event_time_day=2026-09-23<br/>user_id_bucket = 0 · 1 · 2 · 3"]
                    T --> D2["event_time_day=2026-09-24<br/>user_id_bucket = 0 · 1 · 2 · 3"]
                    T --> D3["event_time_day=2026-09-25<br/>user_id_bucket = 0 · 1 · 2 · 3"]
                    Q(["Query: WHERE event_time > '2026-09-24'"]) -. "pruned automatically" .-> D1
                    Q --> D2
                    Q --> D3
                """
            ),
            mo.callout(
                mo.md(
                    "**The user never mentions a partition column.** Iceberg prunes the 2026-09-23 partitions "
                    "on its own. Users write business queries; Iceberg handles the mapping."
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
    ## Part A — Hidden partitioning & partition pruning

    ### Step 1 — Create the web events table

    The notebook runs the SQL for you. To follow along in the Trino CLI instead:

    ```bash
    podman exec -e TRINO_PASSWORD=admin123 -it trino \
      trino --server https://localhost:8443 --user admin --password --insecure
    # or: docker exec ... (same arguments)
    ```

    The table gets two hidden partition transforms:

    - `day(event_time)` organizes data by calendar day
    - `bucket(user_id, 4)` distributes users across 4 hash buckets

    This lab owns `web_events` and `web_events_truncated`. It drops and recreates them, so every run
    starts with the same files and partition specs.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            """
            **Trino puts the column first:** `bucket(user_id, 4)` and `truncate(country, 2)`.
            Spark SQL writes the same transforms as `bucket(4, user_id)` and `truncate(2, country)`;
            Trino rejects that order with *Invalid partition field declaration*. The table property is called
            `partitioning` (older copies of this lab had a typo, `_partitioning`).

            Trino's `DROP TABLE` also asks Polaris to purge the files, which this catalog doesn't allow,
            so the notebook drops its own tables through the Iceberg REST API (no purge) instead.
            """
        ),
        kind="warn",
    )
    return


@app.cell
def _(drop_own_table, mo, sql, stack_ok):
    assert stack_ok
    sql("CREATE SCHEMA IF NOT EXISTS iceberg.shop")
    _dropped = drop_own_table("shop", "web_events")  # instead of DROP TABLE IF EXISTS iceberg.shop.web_events
    sql(
        """
        CREATE TABLE iceberg.shop.web_events (
          event_id VARCHAR,
          user_id VARCHAR,
          event_type VARCHAR,
          page VARCHAR,
          event_time TIMESTAMP(6) WITH TIME ZONE,
          country VARCHAR
        )
        WITH (
          partitioning = ARRAY['day(event_time)', 'bucket(user_id, 4)']
        )
        """
    )
    web_events_created = True
    mo.callout(
        mo.md(
            "Table `iceberg.shop.web_events` "
            + ("dropped and recreated" if _dropped else "created")
            + " with `day(event_time)`, `bucket(user_id, 4)`."
        ),
        kind="success",
    )
    return (web_events_created,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 2 — Insert sample data (30 rows across 3 days)

    Each INSERT creates a separate data file. We spread events across 3 days and 10 users,
    so partition pruning is clearly visible.
    """)
    return


@app.cell
def _(insert_events, mo, web_events_created):
    assert web_events_created
    events = [
        # Day 1: 2026-09-23 — 10 events
        ("evt-001", "user-01", "page_view", "/home",         "2026-09-23 08:15:00 UTC", "US"),
        ("evt-002", "user-02", "click",     "/products",     "2026-09-23 09:22:00 UTC", "UK"),
        ("evt-003", "user-03", "page_view", "/about",        "2026-09-23 10:05:00 UTC", "DE"),
        ("evt-004", "user-04", "purchase",  "/checkout",     "2026-09-23 11:30:00 UTC", "US"),
        ("evt-005", "user-01", "click",     "/products/42",  "2026-09-23 12:45:00 UTC", "US"),
        ("evt-006", "user-05", "page_view", "/home",         "2026-09-23 13:10:00 UTC", "FR"),
        ("evt-007", "user-06", "click",     "/blog",         "2026-09-23 14:00:00 UTC", "JP"),
        ("evt-008", "user-02", "purchase",  "/checkout",     "2026-09-23 15:20:00 UTC", "UK"),
        ("evt-009", "user-07", "page_view", "/pricing",      "2026-09-23 16:35:00 UTC", "IN"),
        ("evt-010", "user-08", "click",     "/docs",         "2026-09-23 17:50:00 UTC", "BR"),
        # Day 2: 2026-09-24 — 10 events
        ("evt-011", "user-01", "page_view", "/home",         "2026-09-24 07:10:00 UTC", "US"),
        ("evt-012", "user-03", "click",     "/products/99",  "2026-09-24 08:25:00 UTC", "DE"),
        ("evt-013", "user-09", "page_view", "/home",         "2026-09-24 09:40:00 UTC", "CA"),
        ("evt-014", "user-04", "click",     "/blog/post-5",  "2026-09-24 10:55:00 UTC", "US"),
        ("evt-015", "user-10", "purchase",  "/checkout",     "2026-09-24 11:15:00 UTC", "AU"),
        ("evt-016", "user-05", "page_view", "/pricing",      "2026-09-24 12:30:00 UTC", "FR"),
        ("evt-017", "user-06", "click",     "/docs/api",     "2026-09-24 13:45:00 UTC", "JP"),
        ("evt-018", "user-02", "page_view", "/home",         "2026-09-24 14:00:00 UTC", "UK"),
        ("evt-019", "user-07", "purchase",  "/checkout",     "2026-09-24 15:20:00 UTC", "IN"),
        ("evt-020", "user-08", "click",     "/products/7",   "2026-09-24 16:35:00 UTC", "BR"),
        # Day 3: 2026-09-25 — 10 events
        ("evt-021", "user-01", "click",     "/products/13",  "2026-09-25 06:00:00 UTC", "US"),
        ("evt-022", "user-09", "page_view", "/blog",         "2026-09-25 07:15:00 UTC", "CA"),
        ("evt-023", "user-03", "purchase",  "/checkout",     "2026-09-25 08:30:00 UTC", "DE"),
        ("evt-024", "user-10", "page_view", "/about",        "2026-09-25 09:45:00 UTC", "AU"),
        ("evt-025", "user-04", "click",     "/home",         "2026-09-25 10:00:00 UTC", "US"),
        ("evt-026", "user-05", "page_view", "/docs",         "2026-09-25 11:15:00 UTC", "FR"),
        ("evt-027", "user-06", "purchase",  "/checkout",     "2026-09-25 12:30:00 UTC", "JP"),
        ("evt-028", "user-07", "click",     "/products/55",  "2026-09-25 13:45:00 UTC", "IN"),
        ("evt-029", "user-02", "page_view", "/pricing",      "2026-09-25 14:00:00 UTC", "UK"),
        ("evt-030", "user-08", "page_view", "/home",         "2026-09-25 15:15:00 UTC", "BR"),
    ]

    with mo.status.spinner(title="Inserting 30 events, one INSERT each…"):
        insert_events("iceberg.shop.web_events", events)
    return (events,)


@app.cell(hide_code=True)
def _(events, mo, pd):
    _df = pd.DataFrame(events, columns=["event_id", "user_id", "event_type", "page", "event_time", "country"])
    _per_day = _df.groupby(_df["event_time"].str[:10]).size()
    mo.hstack(
        [mo.stat(len(_df), label="Rows inserted", caption="30 INSERT statements", bordered=True)]
        + [mo.stat(int(n), label=day, caption="events", bordered=True) for day, n in _per_day.items()],
        widths="equal",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 3 — Inspect partition metadata

    `"web_events$partitions"` has one row per partition. The partition values
    (`event_time_day`, `user_id_bucket`) are **not in the table schema**: they are hidden.
    """)
    return


@app.cell
def _(events, sql):
    assert len(events) == 30
    partitions_df = sql('SELECT * FROM iceberg.shop."web_events$partitions"')
    files_df = sql(
        """
        SELECT file_path, record_count, file_size_in_bytes
        FROM iceberg.shop."web_events$files"
        """
    )
    file_count_initial = len(files_df)
    return file_count_initial, files_df, partitions_df


@app.cell(hide_code=True)
def _(file_count_initial, files_df, flatten_partitions, grid, mo, partitions_df):
    _parts = flatten_partitions(partitions_df).sort_values(["event_time_day", "user_id_bucket"]).reset_index(drop=True)
    _files = files_df.assign(file=files_df["file_path"].str.split("/data/").str[-1]).drop(columns=["file_path"])
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(_parts), label="Partitions", caption="day × bucket", bordered=True),
                    mo.stat(file_count_initial, label="Data files", caption="one per INSERT", bordered=True),
                    mo.stat(int(_parts["record_count"].sum()), label="Records", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.tabs(
                {
                    "web_events$partitions": grid(_parts),
                    "web_events$files": grid(_files[["file", "record_count", "file_size_in_bytes"]]),
                }
            ),
            mo.md(
                "The file paths show the layout Iceberg chose: `event_time_day=…/user_id_bucket=…/`. "
                "You never wrote those values; Iceberg derived them from `event_time` and `user_id`."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Try it: look inside a partition

    Every Iceberg table in Trino has a hidden `"$partition"` column. Pick a partition to see which rows
    landed there, and which users share a hash bucket.
    """)
    return


@app.cell(hide_code=True)
def _(file_count_initial, mo, sql):
    assert file_count_initial > 0
    _keys = sql('SELECT DISTINCT "$partition" AS p FROM iceberg.shop.web_events ORDER BY 1')["p"].tolist()
    partition_picker = mo.ui.dropdown(_keys, value=_keys[len(_keys) // 2], label="Partition")
    partition_picker
    return (partition_picker,)


@app.cell(hide_code=True)
def _(grid, mo, partition_picker, sql):
    _rows = sql(
        f"""
        SELECT event_id, user_id, event_type, page, event_time, country
        FROM iceberg.shop.web_events
        WHERE "$partition" = '{partition_picker.value}'
        ORDER BY event_time
        """
    )
    _buckets = sql(
        """
        SELECT regexp_extract("$partition", 'user_id_bucket=(\\d+)', 1) AS bucket,
               array_join(array_sort(array_agg(DISTINCT user_id)), ', ') AS users
        FROM iceberg.shop.web_events
        GROUP BY 1
        ORDER BY 1
        """
    )
    mo.hstack(
        [
            mo.vstack([mo.md(f"**Rows in `{partition_picker.value}`**"), grid(_rows)]),
            mo.vstack([mo.md("**Which users hash to which bucket**"), grid(_buckets)]),
        ],
        widths=[3, 2],
        align="start",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 4 — Demonstrate partition pruning (filtered query)

    Run a query that filters on `event_time`. Iceberg translates the filter into partition pruning,
    so only the Sep 24 and Sep 25 partitions are scanned.
    """)
    return


@app.cell
def _(file_count_initial, scan_metrics):
    assert file_count_initial > 0
    explain_filtered = scan_metrics(
        """
        SELECT event_id, user_id, event_type, page, event_time
        FROM iceberg.shop.web_events
        WHERE event_time > TIMESTAMP '2026-09-24 00:00:00 UTC'
        """
    )
    return (explain_filtered,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 5 — Full table scan (no filter)

    Now the same query without any filter. All partitions across all 3 days are scanned:
    """)
    return


@app.cell
def _(file_count_initial, scan_metrics):
    assert file_count_initial > 0
    explain_full = scan_metrics(
        """
        SELECT event_id, user_id, event_type, page, event_time
        FROM iceberg.shop.web_events
        """
    )
    return (explain_full,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 6 — Compare the filtered and full scans

    In `EXPLAIN ANALYZE`, look at the table-scan operator: **Splits** is the number of data files read,
    **Input** the number of rows read from them.
    """)
    return


@app.cell(hide_code=True)
def _(explain_filtered, explain_full, file_count_initial, mo):
    def _panel(title, where, m):
        return mo.vstack(
            [
                mo.md(f"**{title}**  \n`{where}`"),
                mo.hstack(
                    [
                        mo.stat(m["splits"], label="Files (splits)", caption=f"of {file_count_initial}", bordered=True),
                        mo.stat(m["rows"], label="Rows read", bordered=True),
                        mo.stat(m["physical"], label="Physical input", bordered=True),
                    ],
                    widths="equal",
                ),
            ]
        )

    _saved = 1 - explain_filtered["splits"] / explain_full["splits"] if explain_full["splits"] else 0
    mo.vstack(
        [
            mo.hstack(
                [
                    _panel("Filtered scan", "WHERE event_time > Sep 24", explain_filtered),
                    _panel("Full scan", "(no WHERE clause)", explain_full),
                ],
                widths="equal",
                gap=2,
            ),
            mo.md(
                f"""
                | | Filtered scan | Full scan |
                |---|---|---|
                | WHERE clause | `event_time > Sep 24` | (none) |
                | Partitions scanned | Sep 24 + Sep 25 | Sep 23 + Sep 24 + Sep 25 |
                | Files opened | {explain_filtered["splits"]} | {explain_full["splits"]} |
                | Rows processed | {explain_filtered["rows"]} | {explain_full["rows"]} |
                """
            ),
            mo.callout(
                mo.md(
                    f"The filtered query skips the entire Sep 23 partition: **{_saved:.0%} less I/O**."
                ),
                kind="success",
            ),
            mo.accordion(
                {
                    "Full EXPLAIN ANALYZE — filtered": mo.md(f"```text\n{explain_filtered['plan']}\n```"),
                    "Full EXPLAIN ANALYZE — no filter": mo.md(f"```text\n{explain_full['plan']}\n```"),
                }
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Try it: compare plans for other filters

    Pick a `WHERE` clause and see how many files Trino opens. The `user_id` filters show that
    `bucket()` prunes too: Iceberg hashes `'user-01'`, keeps only that bucket's partitions, and then
    the per-file min/max statistics skip files of other users that share the bucket.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    filter_picker = mo.ui.dropdown(
        {
            "No filter": "",
            "event_time > Sep 23 00:00": "WHERE event_time > TIMESTAMP '2026-09-23 00:00:00 UTC'",
            "event_time > Sep 24 00:00": "WHERE event_time > TIMESTAMP '2026-09-24 00:00:00 UTC'",
            "event_time > Sep 25 00:00": "WHERE event_time > TIMESTAMP '2026-09-25 00:00:00 UTC'",
            "One hour on Sep 24 (10:00–11:00)": "WHERE event_time >= TIMESTAMP '2026-09-24 10:00:00 UTC' "
            "AND event_time < TIMESTAMP '2026-09-24 11:00:00 UTC'",
            "user_id = 'user-01'": "WHERE user_id = 'user-01'",
            "user_id = 'user-01' on Sep 25": "WHERE user_id = 'user-01' AND event_time >= TIMESTAMP '2026-09-25 00:00:00 UTC'",
            "country = 'US' (not a partition column)": "WHERE country = 'US'",
        },
        value="user_id = 'user-01'",
        label="Filter",
    )
    filter_picker
    return (filter_picker,)


@app.cell(hide_code=True)
def _(file_count_initial, filter_picker, mo, scan_metrics, sql):
    assert file_count_initial > 0
    _query = f"SELECT event_id, user_id, event_time FROM iceberg.shop.web_events {filter_picker.value}".strip()
    _m = scan_metrics(_query)
    _total = int(sql('SELECT count(*) FROM iceberg.shop."web_events$files"').iloc[0, 0])
    mo.vstack(
        [
            mo.md(f"```sql\nEXPLAIN ANALYZE\n{_query}\n```"),
            mo.hstack(
                [
                    mo.stat(_m["splits"], label="Files opened", caption=f"of {_total} in the table", bordered=True),
                    mo.stat(_m["rows"], label="Rows read", bordered=True),
                    mo.stat(_m["physical"], label="Physical input", bordered=True),
                ],
                widths="equal",
            ),
            mo.md(
                "_`country` isn't a partition column here, so Trino can only skip files using the min/max "
                "column statistics stored in the manifests, not whole partitions._"
                if "country" in _query
                else ""
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 7 — The "hidden" aspect

    Look at what the user wrote:

    ```sql
    WHERE event_time > TIMESTAMP '2026-09-24 00:00:00 UTC'
    ```

    The user **never mentioned a partition column**. They never wrote `WHERE event_time_day = ...`
    or referenced any partition directory. Iceberg translated `event_time > '2026-09-24'` into
    `day(event_time) >= 2026-09-24` internally.

    This is the core benefit: **users write business queries; Iceberg handles partition pruning transparently.**

    In Hive-style partitioning you would need:

    - An explicit `event_date` column in the schema
    - `WHERE event_date = '2026-09-24'` in every query
    - Manual ETL to populate the partition column
    - A full rewrite to change the partitioning scheme
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part B — Partition evolution

    ### Step 8 — Evolve partitioning (day to hour)

    Traffic grew and day-level partitions are too coarse. Evolve to hour-level partitioning
    **without rewriting any existing data**:
    """)
    return


@app.cell
def _(explain_filtered, explain_full, sql):
    assert explain_filtered and explain_full  # run Part A's plans before the layout changes
    sql(
        """
        ALTER TABLE iceberg.shop.web_events
          SET PROPERTIES partitioning = ARRAY['hour(event_time)', 'bucket(user_id, 4)']
        """
    )
    ddl = sql("SHOW CREATE TABLE iceberg.shop.web_events").iloc[0, 0]
    return (ddl,)


@app.cell(hide_code=True)
def _(ddl, mo):
    mo.vstack(
        [
            mo.callout(
                mo.md("Partition evolution applied: `day(event_time)` → `hour(event_time)`. **No data was rewritten**; only metadata changed."),
                kind="success",
            ),
            mo.md(f"**Current table definition** (`SHOW CREATE TABLE`)\n\n```sql\n{ddl}\n```"),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 9 — Insert new data (uses hour-level partitions)

    These new rows will be partitioned by hour, not day:
    """)
    return


@app.cell
def _(ddl, insert_events, mo):
    assert "hour(event_time)" in ddl
    new_events = [
        ("evt-031", "user-01", "click",     "/new-feature", "2026-09-25 18:05:00 UTC", "US"),
        ("evt-032", "user-02", "page_view", "/new-feature", "2026-09-25 18:10:00 UTC", "UK"),
        ("evt-033", "user-03", "click",     "/new-feature", "2026-09-25 19:20:00 UTC", "DE"),
        ("evt-034", "user-04", "purchase",  "/checkout",    "2026-09-25 19:35:00 UTC", "US"),
        ("evt-035", "user-05", "page_view", "/home",        "2026-09-25 20:45:00 UTC", "FR"),
    ]
    with mo.status.spinner(title="Inserting 5 more events…"):
        insert_events("iceberg.shop.web_events", new_events)
    return (new_events,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 10 — Verify that the old and new partition layouts coexist

    Each data file records the **partition spec** it was written with (`spec_id`). Old files keep the
    day-level layout; new files use the hour-level one. Iceberg reads both correctly. **No data was rewritten.**
    """)
    return


@app.cell
def _(new_events, sql):
    assert len(new_events) == 5
    partitions_evolved = sql('SELECT * FROM iceberg.shop."web_events$partitions"')
    files_evolved = sql('SELECT spec_id, partition, record_count FROM iceberg.shop."web_events$files"')
    daily_counts = sql(
        """
        SELECT
          CAST(event_time AS DATE) AS event_day,
          count(*) AS events
        FROM iceberg.shop.web_events
        GROUP BY CAST(event_time AS DATE)
        ORDER BY event_day
        """
    )
    return daily_counts, files_evolved, partitions_evolved


@app.cell(hide_code=True)
def _(daily_counts, files_evolved, flatten_partitions, grid, mo, partitions_evolved):
    _files = flatten_partitions(files_evolved)
    _by_spec = (
        _files.groupby("spec_id")
        .agg(files=("record_count", "size"), records=("record_count", "sum"))
        .reset_index()
        .assign(layout=lambda d: d["spec_id"].map({0: "day(event_time), bucket(user_id, 4)", 1: "hour(event_time), bucket(user_id, 4)"}))
    )
    _parts = flatten_partitions(partitions_evolved)
    _parts = _parts.sort_values(
        [c for c in ("event_time_day", "event_time_hour", "user_id_bucket") if c in _parts.columns], na_position="last"
    ).reset_index(drop=True)
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(
                        int(r["files"]),
                        label=f"Spec {r['spec_id']} files",
                        caption=r["layout"],
                        bordered=True,
                    )
                    for _, r in _by_spec.iterrows()
                ]
                + [mo.stat(len(_parts), label="Partitions", caption="old + new", bordered=True)],
                widths="equal",
            ),
            mo.md(
                "**Partitions after evolution.** Old files fill `event_time_day`; new files fill `event_time_hour` "
                "(shown as `YYYY-MM-DD-HH`; Iceberg stores hours since 1970)."
            ),
            grid(_parts),
            mo.md("**Queries still work seamlessly across both layouts:**"),
            grid(daily_counts),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 11 — Compare the truncate() and bucket() transforms

    `bucket(col, N)` hashes values into N buckets, good for even distribution of high-cardinality columns.
    `truncate(col, N)` keeps the first N characters, good for range-scannable, human-readable groupings.

    Create a table that uses `truncate()` instead of `bucket()`:
    """)
    return


@app.cell
def _(drop_own_table, insert_events, mo, sql, stack_ok):
    assert stack_ok
    drop_own_table("shop", "web_events_truncated")  # instead of DROP TABLE IF EXISTS
    sql(
        """
        CREATE TABLE iceberg.shop.web_events_truncated (
          event_id VARCHAR,
          user_id VARCHAR,
          event_type VARCHAR,
          page VARCHAR,
          event_time TIMESTAMP(6) WITH TIME ZONE,
          country VARCHAR
        )
        WITH (
          partitioning = ARRAY['month(event_time)', 'truncate(country, 2)']
        )
        """
    )

    truncate_rows = [
        ("evt-t01", "user-01", "click",     "/home",     "2026-09-25 10:00:00 UTC", "US"),
        ("evt-t02", "user-02", "page_view", "/docs",     "2026-09-25 11:00:00 UTC", "UK"),
        ("evt-t03", "user-03", "click",     "/home",     "2026-09-25 12:00:00 UTC", "DE"),
        ("evt-t04", "user-04", "purchase",  "/checkout", "2026-09-25 13:00:00 UTC", "US"),
    ]
    with mo.status.spinner(title="Creating web_events_truncated…"):
        insert_events("iceberg.shop.web_events_truncated", truncate_rows)

    trunc_partitions = sql('SELECT * FROM iceberg.shop."web_events_truncated$partitions"')
    return (trunc_partitions,)


@app.cell(hide_code=True)
def _(flatten_partitions, grid, mo, partitions_df, trunc_partitions):
    _trunc = flatten_partitions(trunc_partitions).sort_values("country_trunc").reset_index(drop=True)
    _bucket = flatten_partitions(partitions_df)
    _bucket = _bucket[_bucket["event_time_day"] == "2026-09-25"].sort_values("user_id_bucket").reset_index(drop=True)
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.vstack(
                        [
                            mo.md("**`truncate(country, 2)`** on `web_events_truncated`"),
                            grid(_trunc[["event_time_month", "country_trunc", "record_count", "file_count"]]),
                            mo.md("`'US'` → `US`, `'UK'` → `UK`, `'DE'` → `DE`: human-readable."),
                        ]
                    ),
                    mo.vstack(
                        [
                            mo.md("**`bucket(user_id, 4)`** on `web_events`, Sep 25"),
                            grid(_bucket[["event_time_day", "user_id_bucket", "record_count", "file_count"]]),
                            mo.md("Bucket numbers are opaque: you can't tell which users are in bucket 2."),
                        ]
                    ),
                ],
                widths="equal",
                gap=2,
                align="start",
            ),
            mo.md(
                """
                | Transform | How it works | Best for |
                |-----------|-------------|----------|
                | `bucket(col, N)` | Hash the value into N buckets (`"user-01"` → bucket 1); the bucket number is opaque | Even distribution regardless of skew; high-cardinality columns (user IDs, UUIDs, session IDs) |
                | `truncate(col, N)` | Keep the first N characters/digits (`"US"` → `"US"`); the value is human-readable | Range-scannable, predictable grouping (country codes, zip prefixes, SKU prefixes) |
                """
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
                1. Iceberg derives partition values from real columns with transforms (`day`, `hour`, `bucket`, `truncate`, …)
                2. Queries filter on the real columns; Iceberg prunes partitions without the user knowing they exist
                3. `EXPLAIN ANALYZE` shows the effect: fewer splits (files) and rows read
                4. `ALTER TABLE ... SET PROPERTIES partitioning = ...` changes the spec for **new** data only; old files keep theirs
                5. In Trino the column comes first: `bucket(user_id, 4)`, `truncate(country, 2)`
                """
            ),
            "Exercises": mo.md(
                """
                1. **Month-based partitioning:** create a table `iceberg.shop.monthly_events` with
                   `partitioning = ARRAY['month(event_time)', 'bucket(user_id, 8)']`. Insert 20 rows across 3 different months.
                   Query with `WHERE event_time > TIMESTAMP '2026-08-01 00:00:00 UTC'` and check `EXPLAIN ANALYZE`
                   to confirm partition pruning.
                2. **Pruning comparison:** using `web_events`, run `EXPLAIN ANALYZE` for each query and record the number
                   of files scanned:
                   - `WHERE event_time > TIMESTAMP '2026-09-24 00:00:00 UTC'`
                   - `WHERE event_time > TIMESTAMP '2026-09-23 00:00:00 UTC'`
                   - No filter at all

                   How do the file counts compare?
                3. **Evolution chain:** evolve `web_events` from `hour(event_time)` to `month(event_time)`. Insert 5 more rows.
                   Verify that the table now has three partition spec generations (day, hour, month) coexisting.
                4. **Bucket count tuning:** create two tables with identical data, one with `bucket(user_id, 4)` and one with
                   `bucket(user_id, 16)`. Insert 50 rows into each. Compare the partition metadata.
                   When would you choose more buckets vs fewer?
                5. **Challenge: partition health report.** Write a query that joins `"web_events$partitions"` with
                   `"web_events$files"` to show per-partition file counts and total sizes. Identify any partitions that would
                   benefit from compaction (too many small files).
                """
            ),
            "Next lab": mo.md(
                """
                **Lab 12 — Schema Evolution:** add, drop, rename and promote columns without rewriting data.

                **Congratulations!** You've used Iceberg's hidden partition transforms, seen automatic partition pruning,
                and evolved a partition spec without a single data rewrite, all coordinated through Polaris.
                """
            ),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
