import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 15 — Branching & Tagging")


@app.cell(hide_code=True)
def _():
    import os
    from datetime import datetime, timezone
    from decimal import Decimal

    import marimo as mo
    import pandas as pd
    import pyarrow as pa
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
    PRODUCTS = f"iceberg.{SCHEMA}.products"
    TAG = "audit_q3_2026"
    BRANCH = "experiment"

    trino = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (
        BRANCH,
        CATALOG_NAME,
        Decimal,
        POLARIS,
        POLARIS_HEALTH,
        PRODUCTS,
        S3_ENDPOINT,
        SCHEMA,
        TAG,
        datetime,
        load_catalog,
        mo,
        pa,
        pd,
        requests,
        text,
        timezone,
        trino,
    )


@app.cell(hide_code=True)
def _(SCHEMA, mo, pd, text, trino):
    def run_sql(statement):
        """Execute one Trino statement and wait for it to finish."""
        with trino.connect() as conn:
            result = conn.execute(text(statement))
            return result.fetchall() if result.returns_rows else None

    def query(sql):
        with trino.connect() as conn:
            df = pd.read_sql(text(sql), conn)
        if "parent_id" in df:
            df["parent_id"] = df["parent_id"].astype("Int64")
        return df

    def trino_error(exc):
        msg = str(getattr(exc, "orig", exc))
        if "message=" in msg:
            msg = msg.split("message=", 1)[1].split(", query_id")[0].strip("\"'")
        return msg[:300]

    def latest_snapshot():
        return int(
            run_sql(f'SELECT snapshot_id FROM iceberg.{SCHEMA}."products$snapshots" ORDER BY committed_at DESC LIMIT 1')[0][0]
        )

    def refs_table():
        return query(f'SELECT name, type, snapshot_id FROM iceberg.{SCHEMA}."products$refs" ORDER BY type, name')

    def git_graph(table, labels):
        """Render the table's real snapshot DAG (main + other branches + tags) as a mermaid gitGraph."""
        table.refresh()
        meta = table.metadata
        parents = {s.snapshot_id: s.parent_snapshot_id for s in meta.snapshots}

        def lineage(head):
            chain = []
            while head is not None and head in parents:
                chain.append(head)
                head = parents[head]
            return chain[::-1]

        tags = {}
        for name, ref in meta.refs.items():
            if ref.snapshot_ref_type.value == "tag":
                tags.setdefault(ref.snapshot_id, []).append(name)

        def commit(sid):
            label = labels.get(sid, "snapshot")
            tag = "".join(f' tag: "{t}"' for t in tags.get(sid, []))
            return f'    commit id: "{label} · {str(sid)[:6]}"{tag}'

        main = lineage(meta.refs["main"].snapshot_id) if "main" in meta.refs else []
        lines = ["gitGraph", *[commit(s) for s in main]]
        on_main = set(main)
        for name, ref in meta.refs.items():
            if name == "main" or ref.snapshot_ref_type.value != "branch":
                continue
            chain = lineage(ref.snapshot_id)
            fork = max((i for i, s in enumerate(chain) if s in on_main), default=-1)
            if fork >= 0 and chain[fork] != main[-1]:
                lines.append(f'    commit id: "fork point" type: HIGHLIGHT')  # keeps gitGraph syntax simple
            lines += [f"    branch {name}", f"    checkout {name}", *[commit(s) for s in chain[fork + 1 :]], "    checkout main"]
        return mo.mermaid("\n".join(lines))

    return git_graph, latest_snapshot, query, refs_table, run_sql, trino_error


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar([mo.md("### Lab 15\n**Branching & Tagging**"), mo.outline()])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 15 — Branching & Tagging

                **Level:** 5 (Advanced) &nbsp;|&nbsp; **Time:** 30 minutes

                **Goal:** use Iceberg's git-like branching and tagging to create named references to snapshots:
                **tags** for audit and compliance, **branches** for safe experimentation.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Create the Iceberg table `iceberg.shop.products` and tag its first load as `audit_q3_2026`
                    2. Change prices on `main` and prove the tag still shows the original data
                    3. Create an `experiment` branch, write to it, and show that `main` is unaffected
                    4. Pick any branch or tag from a dropdown and query it from Trino
                    5. Inspect the refs with PyIceberg, and *(optionally)* fast-forward `main` or expire snapshots
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

    # PyIceberg with vended credentials: no S3 keys in the config (see Lab 16)
    catalog = load_catalog(
        "polaris_lab15",
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

    Iceberg tables keep a **ref system** much like git. Every table has a `main` branch by default, and you
    can add **tags** and **branches** that point to specific snapshots:

    | Ref type | Mutable? | Description | Analogy |
    |----------|----------|-------------|---------|
    | **Tag** | No (immutable pointer) | A named pointer to a specific snapshot | Git tag |
    | **Branch** | Yes (receives new commits) | A named pointer that can advance independently | Git branch |

    - **Tag:** marks a point in time for auditing, compliance or reproducibility. Once created, it always points to the same snapshot.
    - **Branch:** lets you experiment without affecting production readers. New writes to a branch don't change `main`.

    **Key point:** tags protect snapshots from expiry. Even if you run `expire_snapshots`, a tagged snapshot
    survives. Branches let you write to a table without affecting other readers or pipelines.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        gitGraph
            commit id: "snap1"
            commit id: "snap2" tag: "audit-q3"
            branch experiment
            checkout experiment
            commit id: "exp-snap1"
            commit id: "exp-snap2"
            checkout main
            commit id: "snap3" tag: "pre-migration"
            commit id: "snap4"
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            """
            **Engine support for refs on this stack (Trino 483 + Polaris)**

            | Action | Trino SQL | PyIceberg |
            |--------|-----------|-----------|
            | Read a tag or branch: `FOR VERSION AS OF 'name'` | Yes | Yes (`scan(snapshot_id=…)`) |
            | List refs: `"table$refs"` | Yes | Yes (`table.metadata.refs`) |
            | Create a tag or branch | No¹ | Yes (`manage_snapshots().create_tag / create_branch`) |
            | Write to a branch | No² | Yes (`append / delete / overwrite(…, branch=…)`) |
            | Fast-forward or replace `main` | No¹ | Yes (`manage_snapshots().set_current_snapshot`) |

            ¹ The lab's `ALTER TABLE … SET PROPERTIES "refs.…"` isn't a Trino table property. Trino's newer
            `CREATE BRANCH` / `ALTER BRANCH … FAST FORWARD` statements fail on this stack's file-based access control.
            ² `INSERT INTO products @ experiment` reports *"Branch does not exist"* for branches created outside Trino.

            So the notebook **tries the lab's Trino SQL first**, shows you the error, and then makes the same change
            with PyIceberg. Spark SQL supports all of it (`ALTER TABLE … CREATE TAG / CREATE BRANCH`, `INSERT INTO t.branch_x`).
            """
        ),
        kind="warn",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part A — Tags (named snapshots)

    ### Step 1 — Create the products table

    The lab owns the Iceberg table `iceberg.shop.products`, so it drops and recreates it at the start of
    every run for a clean history. This is not the Postgres `postgres.public.products` table. The drop goes
    through PyIceberg because Polaris rejects Trino's purging `DROP TABLE`.
    """)
    return


@app.cell
def _(PRODUCTS, SCHEMA, catalog, run_sql):
    if catalog.table_exists(f"{SCHEMA}.products"):
        catalog.drop_table(f"{SCHEMA}.products")

    run_sql(f"CREATE SCHEMA IF NOT EXISTS iceberg.{SCHEMA} WITH (location = 's3://warehouse/polaris_warehouse/{SCHEMA}')")
    run_sql(f"""
        CREATE TABLE {PRODUCTS} (
          product_id VARCHAR,
          name VARCHAR,
          category VARCHAR,
          price DECIMAL(10,2),
          in_stock BOOLEAN
        )
    """)
    products_created = True
    return (products_created,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 2 — Insert the initial products

    Eight products across three categories:
    """)
    return


@app.cell
def _(PRODUCTS, products_created, run_sql):
    products_created  # run after Step 1
    run_sql(f"""
        INSERT INTO {PRODUCTS} VALUES
          ('P001', 'Wireless Mouse',      'Peripherals', 29.99, true),
          ('P002', 'Mechanical Keyboard', 'Peripherals', 89.99, true),
          ('P003', 'USB-C Hub',           'Accessories', 45.00, true),
          ('P004', 'Monitor Stand',       'Furniture',   64.50, true),
          ('P005', 'Webcam HD',           'Peripherals', 79.99, true),
          ('P006', 'Desk Lamp',           'Furniture',   34.99, false),
          ('P007', 'Cable Organizer',     'Accessories', 12.99, true),
          ('P008', 'Laptop Cooling Pad',  'Accessories', 27.50, true)
    """)
    products_loaded = True
    return (products_loaded,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 3 — Create a tag: `audit_q3_2026`

    First, find the current snapshot ID:
    """)
    return


@app.cell
def _(SCHEMA, products_loaded, query):
    products_loaded  # run after Step 2
    snapshots_initial = query(f"""
        SELECT snapshot_id, operation, committed_at
        FROM iceberg.{SCHEMA}."products$snapshots"
        ORDER BY committed_at
    """)
    tag_snapshot_id = int(snapshots_initial.iloc[-1]["snapshot_id"])  # the INSERT
    return snapshots_initial, tag_snapshot_id


@app.cell(hide_code=True)
def _(mo, snapshots_initial, tag_snapshot_id):
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(snapshots_initial), label="Snapshots", caption="CREATE TABLE + INSERT", bordered=True),
                    mo.stat(tag_snapshot_id, label="Snapshot to tag", caption="the INSERT", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.table(snapshots_initial, selection=None, show_column_summaries=False),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    Now create a tag that points to the INSERT snapshot. The lab's Trino statement runs first;
    if Trino rejects it, the same tag is created through the Iceberg API with PyIceberg.
    """)
    return


@app.cell
def _(PRODUCTS, SCHEMA, TAG, catalog, run_sql, tag_snapshot_id, trino_error):
    try:
        run_sql(f"""
            ALTER TABLE {PRODUCTS}
            SET PROPERTIES
              "refs.{TAG}.type" = 'TAG',
              "refs.{TAG}.snapshot-id" = '{tag_snapshot_id}'
        """)
        tag_trino_error = None
    except Exception as _e:
        tag_trino_error = trino_error(_e)
        # Same result through the Iceberg REST API
        catalog.load_table(f"{SCHEMA}.products").manage_snapshots().create_tag(
            snapshot_id=tag_snapshot_id, tag_name=TAG
        ).commit()
    return (tag_trino_error,)


@app.cell(hide_code=True)
def _(TAG, mo, refs_table, tag_snapshot_id, tag_trino_error):
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"**Trino rejected the statement:** `{tag_trino_error}`\n\n"
                    f"Created the tag with PyIceberg instead: "
                    f"`table.manage_snapshots().create_tag({tag_snapshot_id}, \"{TAG}\").commit()`"
                )
                if tag_trino_error
                else mo.md("Trino created the tag."),
                kind="warn" if tag_trino_error else "success",
            ),
            mo.md(
                f"Tag **`{TAG}`** now permanently points to snapshot `{tag_snapshot_id}`: the original 8 products at "
                'their original prices. Trino can see it in the `"products$refs"` metadata table:'
            ),
            mo.ui.table(refs_table(), selection=None, show_column_summaries=False),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 4 — Make changes (new snapshots)

    Simulate a 15% price hike on Peripherals and add a new product:
    """)
    return


@app.cell
def _(PRODUCTS, latest_snapshot, run_sql, tag_trino_error):
    tag_trino_error  # run after the tag exists
    run_sql(f"""
        UPDATE {PRODUCTS}
        SET price = price * 1.15
        WHERE category = 'Peripherals'
    """)
    snap_price_hike_id = latest_snapshot()

    run_sql(f"""
        INSERT INTO {PRODUCTS} VALUES
          ('P009', 'Noise-Cancelling Headphones', 'Peripherals', 199.99, true)
    """)
    snap_p009_id = latest_snapshot()
    return snap_p009_id, snap_price_hike_id


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 5 — Query the tagged version

    The tag still points to the original snapshot. Query it to confirm it hasn't moved, first by snapshot ID
    as in the lab, then **by tag name**, which Trino also supports:
    """)
    return


@app.cell
def _(PRODUCTS, TAG, query, snap_p009_id, tag_snapshot_id):
    snap_p009_id  # run after Step 4
    df_tagged = query(f"""
        SELECT *
        FROM {PRODUCTS}
        FOR VERSION AS OF {tag_snapshot_id}
        ORDER BY product_id
    """)
    df_tagged_by_name = query(f"SELECT * FROM {PRODUCTS} FOR VERSION AS OF '{TAG}' ORDER BY product_id")
    df_current = query(f"SELECT * FROM {PRODUCTS} ORDER BY product_id")
    return df_current, df_tagged, df_tagged_by_name


@app.cell(hide_code=True)
def _(TAG, df_current, df_tagged, df_tagged_by_name, mo):
    def _p001(df):
        return f"${float(df.loc[df['product_id'] == 'P001', 'price'].iloc[0]):.2f}"

    _same = df_tagged.astype(str).equals(df_tagged_by_name.astype(str))
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.vstack(
                        [
                            mo.md(f"**Tag `{TAG}`**"),
                            mo.hstack(
                                [
                                    mo.stat(len(df_tagged), label="Rows", bordered=True),
                                    mo.stat(_p001(df_tagged), label="P001 price", bordered=True),
                                    mo.stat("Yes" if "P009" in set(df_tagged["product_id"]) else "No", label="P009 present", bordered=True),
                                ],
                                widths="equal",
                            ),
                            mo.ui.table(df_tagged, selection=None, show_column_summaries=False),
                        ]
                    ),
                    mo.vstack(
                        [
                            mo.md("**`main` (current)**"),
                            mo.hstack(
                                [
                                    mo.stat(len(df_current), label="Rows", bordered=True),
                                    mo.stat(_p001(df_current), label="P001 price", bordered=True),
                                    mo.stat("Yes" if "P009" in set(df_current["product_id"]) else "No", label="P009 present", bordered=True),
                                ],
                                widths="equal",
                            ),
                            mo.ui.table(df_current, selection=None, show_column_summaries=False),
                        ]
                    ),
                ],
                widths="equal",
                align="start",
            ),
            mo.callout(
                mo.md(
                    "All 8 original products at their original prices: no price hike and no P009. "
                    + (f"`FOR VERSION AS OF '{TAG}'` returns exactly the same rows as the snapshot ID." if _same else "")
                ),
                kind="success",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 6 — Compare the current state with the tagged state
    """)
    return


@app.cell
def _(PRODUCTS, df_current, query, tag_snapshot_id):
    df_current  # run after Step 5
    df_tag_diff = query(f"""
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
        FROM {PRODUCTS} c
        FULL OUTER JOIN {PRODUCTS} FOR VERSION AS OF {tag_snapshot_id} t
          ON c.product_id = t.product_id
        ORDER BY COALESCE(c.product_id, t.product_id)
    """)
    return (df_tag_diff,)


@app.cell(hide_code=True)
def _(TAG, df_tag_diff, mo):
    _n = df_tag_diff["status"].value_counts()
    mo.vstack(
        [
            mo.md(f"**Current state vs `{TAG}`**"),
            mo.hstack(
                [mo.stat(int(_n.get(s, 0)), label=s, bordered=True) for s in ("PRICE CHANGED", "ADDED", "DELETED", "UNCHANGED")],
                widths="equal",
            ),
            mo.ui.table(df_tag_diff, selection=None, show_column_summaries=False),
            mo.callout(
                mo.md("Expected: P001 29.99 → 34.49, P002 89.99 → 103.49, P005 79.99 → 91.99 (**PRICE CHANGED**), P009 **ADDED**, all others **UNCHANGED**."),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part B — Branches (independent write paths)

    ### Step 7 — Create a branch: `experiment`

    Get the current snapshot ID:
    """)
    return


@app.cell
def _(SCHEMA, df_tag_diff, query):
    df_tag_diff  # run after Part A
    snapshots_pre_branch = query(f"""
        SELECT snapshot_id, operation, committed_at
        FROM iceberg.{SCHEMA}."products$snapshots"
        ORDER BY committed_at DESC
        LIMIT 1
    """)
    branch_snapshot_id = int(snapshots_pre_branch.iloc[0]["snapshot_id"])
    return (branch_snapshot_id,)


@app.cell
def _(BRANCH, PRODUCTS, SCHEMA, branch_snapshot_id, catalog, run_sql, trino_error):
    try:
        run_sql(f"""
            ALTER TABLE {PRODUCTS}
            SET PROPERTIES
              "refs.{BRANCH}.type" = 'BRANCH',
              "refs.{BRANCH}.snapshot-id" = '{branch_snapshot_id}'
        """)
        branch_trino_error = None
    except Exception as _e:
        branch_trino_error = trino_error(_e)
        catalog.load_table(f"{SCHEMA}.products").manage_snapshots().create_branch(
            snapshot_id=branch_snapshot_id, branch_name=BRANCH
        ).commit()
    return (branch_trino_error,)


@app.cell(hide_code=True)
def _(BRANCH, branch_snapshot_id, branch_trino_error, mo, refs_table):
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"**Trino rejected the statement:** `{branch_trino_error}`\n\n"
                    f"Created the branch with PyIceberg: "
                    f"`table.manage_snapshots().create_branch({branch_snapshot_id}, \"{BRANCH}\").commit()`"
                )
                if branch_trino_error
                else mo.md("Trino created the branch."),
                kind="warn" if branch_trino_error else "success",
            ),
            mo.md(f"Branch **`{BRANCH}`** starts from the same snapshot as `main` (`{branch_snapshot_id}`):"),
            mo.ui.table(refs_table(), selection=None, show_column_summaries=False),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 8 — Write to the experiment branch

    Writes to `experiment` create new snapshots that are **only visible when you read from that branch**;
    `main` is left unchanged. Trino has branch-aware DML (`INSERT INTO iceberg.shop.products @ experiment …`),
    and the cell tries it first. On this stack it fails, so the writes go through PyIceberg with `branch=`:

    - add two experimental products
    - drop the out-of-stock Desk Lamp (P006)
    """)
    return


@app.cell
def _(BRANCH, Decimal, PRODUCTS, SCHEMA, branch_trino_error, catalog, latest_snapshot, pa, run_sql, trino_error):
    branch_trino_error  # run after the branch exists
    try:
        run_sql(f"INSERT INTO {PRODUCTS} @ {BRANCH} VALUES ('P010', 'Smart Desk Pad', 'Accessories', 49.99, true)")
        branch_write_error = None
    except Exception as _e:
        branch_write_error = trino_error(_e)

    products_table = catalog.load_table(f"{SCHEMA}.products")
    _new_rows = pa.Table.from_pylist(
        [
            {"product_id": "P010", "name": "Smart Desk Pad", "category": "Accessories", "price": Decimal("49.99"), "in_stock": True},
            {"product_id": "P011", "name": "Ergonomic Foot Rest", "category": "Furniture", "price": Decimal("39.00"), "in_stock": True},
        ],
        schema=products_table.schema().as_arrow(),
    )
    if branch_write_error:
        products_table.append(_new_rows, branch=BRANCH)
    products_table.delete("product_id == 'P006'", branch=BRANCH)
    products_table.refresh()
    exp_head_id = products_table.metadata.refs[BRANCH].snapshot_id
    main_head_id = latest_snapshot() if products_table.metadata.refs["main"].snapshot_id is None else products_table.metadata.refs["main"].snapshot_id
    exp_snapshot_ids = []
    _sid = exp_head_id
    while _sid is not None and _sid != main_head_id:
        exp_snapshot_ids.append(_sid)
        _sid = products_table.snapshot_by_id(_sid).parent_snapshot_id
    exp_snapshot_ids.reverse()
    return branch_write_error, exp_head_id, exp_snapshot_ids, main_head_id, products_table


@app.cell(hide_code=True)
def _(BRANCH, branch_write_error, exp_head_id, exp_snapshot_ids, main_head_id, mo):
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"**Trino branch write failed:** `{branch_write_error}`. The two products were appended with "
                    f"`table.append(rows, branch=\"{BRANCH}\")` and P006 deleted with "
                    f"`table.delete(\"product_id == 'P006'\", branch=\"{BRANCH}\")`."
                )
                if branch_write_error
                else mo.md("Trino wrote to the branch; P006 was deleted with PyIceberg."),
                kind="warn" if branch_write_error else "success",
            ),
            mo.hstack(
                [
                    mo.stat(len(exp_snapshot_ids), label="New snapshots", caption=f"on {BRANCH} only", bordered=True),
                    mo.stat(str(exp_head_id)[:10] + "…", label=f"{BRANCH} head", bordered=True),
                    mo.stat(str(main_head_id)[:10] + "…", label="main head", caption="unchanged", bordered=True),
                ],
                widths="equal",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Step 9 & 10 — Query `main` and the experiment branch

    `main` is unaffected by the writes to `experiment`. To read the branch, use the snapshot ID it points to
    (as in the lab) or, more simply, the branch name:
    """)
    return


@app.cell
def _(BRANCH, PRODUCTS, exp_head_id, query):
    df_main = query(f"""
        SELECT COUNT(*) AS main_count, ROUND(AVG(price), 2) AS main_avg_price
        FROM {PRODUCTS}
    """)
    df_experiment = query(f"""
        SELECT COUNT(*) AS exp_count, ROUND(AVG(price), 2) AS exp_avg_price
        FROM {PRODUCTS}
        FOR VERSION AS OF {exp_head_id}
    """)
    df_experiment_by_name = query(f"SELECT COUNT(*) AS exp_count FROM {PRODUCTS} FOR VERSION AS OF '{BRANCH}'")
    return df_experiment, df_experiment_by_name, df_main


@app.cell(hide_code=True)
def _(BRANCH, df_experiment, df_experiment_by_name, df_main, mo):
    _diverged = int(df_main.iloc[0, 0]) != int(df_experiment.iloc[0, 0])
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(int(df_main.iloc[0, 0]), label="main rows", caption=f"avg ${float(df_main.iloc[0, 1]):.2f}", bordered=True),
                    mo.stat(int(df_experiment.iloc[0, 0]), label=f"{BRANCH} rows", caption=f"avg ${float(df_experiment.iloc[0, 1]):.2f}", bordered=True),
                    mo.stat(int(df_experiment_by_name.iloc[0, 0]), label=f"FOR VERSION AS OF '{BRANCH}'", caption="same as by ID", bordered=True),
                ],
                widths="equal",
            ),
            mo.callout(
                mo.md(
                    f"**The branches have diverged.** `{BRANCH}` has the two new products and no P006; `main` still has the 9 products from Part A."
                    if _diverged
                    else "Both refs point to the same data. Check Step 8."
                ),
                kind="success" if _diverged else "warn",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### The table's history as a graph

    Built from the table's real metadata: every snapshot, the `main` and `experiment` branches and the
    `audit_q3_2026` tag.
    """)
    return


@app.cell(hide_code=True)
def _(exp_snapshot_ids, products_table, snap_p009_id, snap_price_hike_id, snapshots_initial, tag_snapshot_id):
    snapshot_labels = {
        int(snapshots_initial.iloc[0]["snapshot_id"]): "CREATE TABLE",
        tag_snapshot_id: "INSERT 8 products",
        snap_price_hike_id: "UPDATE +15%",
        snap_p009_id: "INSERT P009",
    }
    for _sid in exp_snapshot_ids:
        _op = products_table.snapshot_by_id(_sid).summary.operation.value
        snapshot_labels[_sid] = "append P010+P011" if _op == "append" else "delete P006"
    return (snapshot_labels,)


@app.cell(hide_code=True)
def _(git_graph, products_table, snapshot_labels):
    git_graph(products_table, snapshot_labels)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Try it: query any branch or tag

    Pick a ref. Trino reads it with `FOR VERSION AS OF '<ref name>'`.
    """)
    return


@app.cell(hide_code=True)
def _(df_experiment, mo, refs_table):
    df_experiment  # refresh after the branch writes
    _refs = refs_table()
    ref_picker = mo.ui.dropdown(
        {f"{r.name} ({r.type.lower()})": r.name for r in _refs.itertuples()},
        value=next(f"{r.name} ({r.type.lower()})" for r in _refs.itertuples() if r.name == "experiment"),
        label="Branch or tag",
    )
    compare_picker = mo.ui.dropdown(
        {f"{r.name} ({r.type.lower()})": r.name for r in _refs.itertuples()},
        value=next(f"{r.name} ({r.type.lower()})" for r in _refs.itertuples() if r.name == "main"),
        label="Compare with",
    )
    mo.hstack([ref_picker, compare_picker], justify="start", gap=2)
    return compare_picker, ref_picker


@app.cell(hide_code=True)
def _(PRODUCTS, compare_picker, mo, query, ref_picker):
    def _panel(ref):
        df = query(f"SELECT * FROM {PRODUCTS} FOR VERSION AS OF '{ref}' ORDER BY product_id")
        return df, mo.vstack(
            [
                mo.md(f"```sql\nSELECT * FROM iceberg.shop.products FOR VERSION AS OF '{ref}'\n```"),
                mo.hstack(
                    [
                        mo.stat(len(df), label="Rows", bordered=True),
                        mo.stat(f"${df['price'].astype(float).mean():.2f}", label="Avg price", bordered=True),
                        mo.stat(int(df["in_stock"].sum()), label="In stock", bordered=True),
                    ],
                    widths="equal",
                ),
                mo.ui.table(df, selection=None, show_column_summaries=False),
            ]
        )

    _left_df, _left = _panel(ref_picker.value)
    _right_df, _right = _panel(compare_picker.value)
    _only_left = sorted(set(_left_df["product_id"]) - set(_right_df["product_id"]))
    _only_right = sorted(set(_right_df["product_id"]) - set(_left_df["product_id"]))
    mo.vstack(
        [
            mo.hstack([_left, _right], widths="equal", align="start"),
            mo.callout(
                mo.md(
                    f"Only in `{ref_picker.value}`: {', '.join(_only_left) or '—'} &nbsp;·&nbsp; "
                    f"only in `{compare_picker.value}`: {', '.join(_only_right) or '—'}"
                ),
                kind="neutral",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part C — Use cases

    ### Step 11 — When to use tags vs branches

    | Feature | Tag | Branch |
    |---------|-----|--------|
    | Mutable? | No (immutable pointer) | Yes (receives new commits) |
    | Use case | Audit, compliance, releases | Experimentation, staging |
    | Analogy | Git tag | Git branch |
    | Example | "Q3-2026 audit snapshot" | "test new ETL before promoting" |
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "Tags are ideal for": mo.md(
                """
                - Regulatory and compliance snapshots ("this is what the data looked like on the audit date")
                - Release markers ("this version was used for the Q3 report")
                - Reproducibility ("re-run my analysis against this exact data")
                - Protecting snapshots from garbage collection (`expire_snapshots` won't remove a tagged snapshot)
                """
            ),
            "Branches are ideal for": mo.md(
                """
                - Testing ETL changes without affecting production reads
                - A/B testing data transformations
                - Staging new data before promoting it to `main`
                - Letting data scientists experiment in isolation
                """
            ),
            "Write-Audit-Publish": mo.mermaid(
                """
                flowchart LR
                    W["Write new data<br/>to branch 'staging'"] --> A{"Audit<br/>row counts, nulls,<br/>aggregates"}
                    A -- pass --> P["Publish<br/>fast-forward main"]
                    A -- fail --> D["Drop the branch<br/>main never saw it"]
                """
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part D — Verify with PyIceberg

    ### Step 12 — Inspect refs (tags and branches)

    PyIceberg reads the same refs from the table metadata in Polaris. Unlike the original lab, the config
    below has **no static S3 keys**: Polaris vends them (see Lab 16).
    """)
    return


@app.cell
def _(CATALOG_NAME, POLARIS, S3_ENDPOINT, df_experiment, load_catalog):
    df_experiment  # run after the branch writes
    pyiceberg_catalog = load_catalog(
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

    table = pyiceberg_catalog.load_table("shop.products")

    # Snapshot history of main
    history = [(entry.snapshot_id, entry.timestamp_ms) for entry in table.history()]

    # Refs are stored in the table metadata
    refs = {name: (ref.snapshot_ref_type.value, ref.snapshot_id) for name, ref in table.metadata.refs.items()}
    current_snapshot_id = table.metadata.current_snapshot_id
    return current_snapshot_id, history, refs, table


@app.cell(hide_code=True)
def _(current_snapshot_id, datetime, history, mo, pd, refs, snapshot_labels, table, timezone):
    _refs_df = pd.DataFrame(
        [{"ref": n, "type": t, "snapshot_id": s, "what": snapshot_labels.get(s, "")} for n, (t, s) in refs.items()]
    )
    _hist_df = pd.DataFrame(
        [
            {
                "snapshot_id": sid,
                "timestamp": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "what": snapshot_labels.get(sid, ""),
            }
            for sid, ts in history
        ]
    )
    _all_df = pd.DataFrame(
        [
            {
                "snapshot_id": s.snapshot_id,
                "parent_id": s.parent_snapshot_id,
                "operation": s.summary.operation.value if s.summary else "",
                "what": snapshot_labels.get(s.snapshot_id, ""),
                "refs": ", ".join(n for n, (_, sid) in refs.items() if sid == s.snapshot_id),
            }
            for s in table.snapshots()
        ]
    )
    mo.vstack(
        [
            mo.stat(current_snapshot_id, label="Current (main) snapshot", bordered=True),
            mo.ui.tabs(
                {
                    "table.metadata.refs": mo.ui.table(_refs_df, selection=None, show_column_summaries=False),
                    "table.history() (main lineage)": mo.ui.table(_hist_df, selection=None, show_column_summaries=False),
                    "table.snapshots() (all branches)": mo.ui.table(_all_df, selection=None, show_column_summaries=False),
                }
            ),
            mo.callout(
                mo.md("`history()` follows **main** only. The experiment snapshots appear in `snapshots()` because they belong to the table but not to main's lineage."),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Optional — Promote the branch and expire snapshots

    These steps change the table's refs and history, so they only run when you click. Re-running the notebook
    from the top rebuilds the table.

    ### Promote: fast-forward `main` to `experiment`

    *(Exercise 5.)* Validate the branch, then move `main` to the branch head. A **fast-forward** is only safe
    when `main` is an ancestor of the branch head, so the cell checks that first. In Spark this is
    `CALL system.fast_forward('shop.products', 'main', 'experiment')`. Trino 483 has no such procedure, and its
    `ALTER BRANCH main … FAST FORWARD TO experiment` fails on this stack's access control, so the cell uses
    PyIceberg's `set_current_snapshot`.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    promote_button = mo.ui.run_button(label="Validate and fast-forward main", kind="warn")
    promote_button
    return (promote_button,)


@app.cell
def _(BRANCH, PRODUCTS, git_graph, mo, products_table, promote_button, query, snapshot_labels):
    mo.stop(not promote_button.value, mo.callout("Click **Validate and fast-forward main** to promote the branch.", kind="neutral"))

    # 1. Validate the branch (row counts, null checks, aggregation sanity)
    _checks = query(f"""
        SELECT COUNT(*) AS row_count,
               COUNT(*) FILTER (WHERE product_id IS NULL OR price IS NULL) AS null_keys_or_prices,
               MIN(price) AS min_price
        FROM {PRODUCTS} FOR VERSION AS OF '{BRANCH}'
    """)
    _valid = int(_checks.loc[0, "row_count"]) > 0 and int(_checks.loc[0, "null_keys_or_prices"]) == 0 and float(_checks.loc[0, "min_price"]) > 0

    # 2. Fast-forward only if main is an ancestor of the branch head
    products_table.refresh()
    _main = products_table.metadata.refs["main"].snapshot_id
    _head = products_table.metadata.refs[BRANCH].snapshot_id
    _ancestors, _sid = set(), _head
    while _sid is not None:
        _ancestors.add(_sid)
        _sid = products_table.snapshot_by_id(_sid).parent_snapshot_id
    _can_ff = _main in _ancestors

    if _valid and _can_ff and _main != _head:
        products_table.manage_snapshots().set_current_snapshot(ref_name=BRANCH).commit()
        _msg, _kind = f"**main fast-forwarded** from `{_main}` to `{_head}`.", "success"
    elif _main == _head:
        _msg, _kind = "main already points at the branch head. Nothing to do.", "neutral"
    else:
        _msg, _kind = f"**Not promoted.** Checks passed: {_valid} · main is an ancestor: {_can_ff}.", "danger"

    mo.vstack(
        [
            mo.ui.table(_checks, selection=None, show_column_summaries=False),
            mo.callout(mo.md(_msg), kind=_kind),
            git_graph(products_table, snapshot_labels),
            mo.ui.table(query(f"SELECT COUNT(*) AS main_count, ROUND(AVG(price), 2) AS main_avg_price FROM {PRODUCTS}"), selection=None, show_column_summaries=False),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Tags protect snapshots from expiry

    *(Exercise 3.)* Expire **every** snapshot that no branch or tag points to, then check that the
    `audit_q3_2026` snapshot survived. Trino's `ALTER TABLE … EXECUTE expire_snapshots(retention_threshold => …)`
    enforces a 7-day minimum retention on this stack, so a just-created table has nothing old enough to expire.
    The cell uses PyIceberg's `maintenance.expire_snapshots()`, which never removes the head of a branch or tag.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    expire_button = mo.ui.run_button(label="Expire unreferenced snapshots", kind="danger")
    expire_button
    return (expire_button,)


@app.cell
def _(PRODUCTS, TAG, datetime, expire_button, mo, products_table, query, tag_snapshot_id, timezone):
    mo.stop(not expire_button.value, mo.callout("Click **Expire unreferenced snapshots** to run the test.", kind="neutral"))

    products_table.refresh()
    _before = {s.snapshot_id for s in products_table.snapshots()}
    products_table.maintenance.expire_snapshots().older_than(datetime.now(timezone.utc)).commit()
    products_table.refresh()
    _after = {s.snapshot_id for s in products_table.snapshots()}

    _tag_rows = len(query(f"SELECT * FROM {PRODUCTS} FOR VERSION AS OF '{TAG}'"))
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(_before), label="Snapshots before", bordered=True),
                    mo.stat(len(_after), label="Snapshots after", bordered=True),
                    mo.stat("Yes" if tag_snapshot_id in _after else "No", label=f"{TAG} survived?", bordered=True),
                    mo.stat(_tag_rows, label="Rows readable via the tag", bordered=True),
                ],
                widths="equal",
            ),
            mo.callout(
                mo.md(
                    f"Expired {len(_before - _after)} snapshot(s). The tagged snapshot is still there and readable. "
                    "Untagged history such as `UPDATE +15%` is gone, so time travel to it now fails."
                ),
                kind="success" if tag_snapshot_id in _after else "danger",
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
                1. A **tag** is an immutable name for one snapshot; a **branch** is a movable name that receives its own commits
                2. Writes to a branch never change `main`, so readers of `main` are isolated from experiments
                3. Trino reads any ref with `FOR VERSION AS OF 'name'` and lists them in `"table$refs"`
                4. Creating refs and writing to branches needs an engine that supports it (Spark SQL, PyIceberg); on this stack Trino can only read refs
                5. Snapshots that a branch or tag points to survive `expire_snapshots`
                """
            ),
            "Exercises": mo.md(
                """
                1. **Create a second tag:** create a tag `pre_price_hike` before updating prices. After the update,
                   compare prices between the two tags using `FULL OUTER JOIN` on two versioned references.
                2. **Branch isolation test:** create a branch, write 100 rows to it (via PyIceberg if Trino branch writes
                   aren't available), then query both main and the branch to verify isolation.
                3. **Tags protect snapshots:** tag a snapshot, then expire old snapshots with
                   `CALL iceberg.system.expire_snapshots(...)`. Does the tagged snapshot survive expiration? (It should;
                   tags protect snapshots from expiry.) *Try it with the button above. On Trino use
                   `ALTER TABLE … EXECUTE expire_snapshots(retention_threshold => '7d')`.*
                4. **Discussion: A/B testing.** How would you use branches for A/B testing data transformations? Sketch a
                   workflow where two branches receive different transformations, both are validated, and the better one
                   is promoted to main.
                5. **Challenge: promote branch.** Build a "promote branch" workflow: write to a branch, validate the data
                   (row counts, null checks, aggregation sanity checks), then fast-forward main to the branch's latest
                   snapshot using `CALL iceberg.system.fast_forward(...)` or by updating the main ref. *The button above
                   is one solution.*
                """
            ),
            "Next lab": mo.md(
                "**Lab 16 — Credential Vending:** make Polaris issue short-lived, table-scoped S3 credentials "
                "instead of sharing static keys."
            ),
        },
        multiple=True,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    **Congratulations!** You can now create named references to Iceberg snapshots: immutable tags for audit and
    compliance, and mutable branches for safe experimentation, all managed through Polaris as the central catalog.
    """)
    return


if __name__ == "__main__":
    app.run()
